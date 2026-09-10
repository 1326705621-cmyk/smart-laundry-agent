"""有限轮次的 Tool Calling Agent，以及无模型配置时的规则降级。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from smart_laundry.recommendations import build_rule_plan, render_rule_plan
from smart_laundry.repositories import ItemRepository
from smart_laundry.tools import LaundryToolRegistry, TOOL_SCHEMAS
from smart_laundry.weather import WeatherService, WeatherSummary


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolTrace:
    name: str
    summary: str
    ok: bool


@dataclass(frozen=True, slots=True)
class AgentResult:
    mode: Literal["AI Agent", "规则建议"]
    answer: str
    trace: tuple[ToolTrace, ...]
    pending_actions: tuple[dict[str, Any], ...] = ()
    fallback_reason: str | None = None


def _fallback(
    repository: ItemRepository,
    weather: WeatherSummary | None,
    *,
    today: date,
    reason: str,
) -> AgentResult:
    items = repository.list_items()
    plan = build_rule_plan(items, weather, today=today)
    weather_text = (
        f"今天{weather.city}天气：{weather.condition}，降雨概率 "
        f"{weather.precipitation_probability}%，{weather.drying_label}。"
        if weather
        else "今天的天气暂不可用，计划不会安排户外晾晒。"
    )
    return AgentResult(
        mode="规则建议",
        answer=f"{weather_text}\n\n{render_rule_plan(plan)}",
        trace=(
            ToolTrace("get_item_records", f"读取 {len(items)} 件物品", True),
            ToolTrace("get_weather", "使用页面已获取天气" if weather else "天气不可用", bool(weather)),
        ),
        fallback_reason=reason,
    )


def run_laundry_agent(
    request: str,
    *,
    city: str,
    repository: ItemRepository,
    weather: WeatherSummary | None,
    today: date,
    api_key: str | None,
    model: str | None,
    base_url: str | None = None,
    client: Any | None = None,
    max_rounds: int = 5,
) -> AgentResult:
    """运行最多 max_rounds 轮；任何写工具只产生待确认动作。"""

    cleaned_request = request.strip()
    if not cleaned_request:
        return _fallback(repository, weather, today=today, reason="请输入想安排的洗晒任务。")
    if not model or (client is None and not api_key):
        return _fallback(
            repository,
            weather,
            today=today,
            reason="未配置模型，已由规则引擎直接读取天气和物品记录。",
        )

    class _PrefetchedWeatherService(WeatherService):
        def get_today(self, requested_city: str) -> WeatherSummary:
            if weather and requested_city.strip().casefold() == city.strip().casefold():
                return weather
            return super().get_today(requested_city)

    registry = LaundryToolRegistry(
        repository, weather_service=_PrefetchedWeatherService(), today=today
    )
    planning_request = any(
        keyword in cleaned_request for keyword in ("安排", "计划", "适合", "哪些", "建议")
    )
    try:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url, timeout=20.0)
        input_items: list[Any] = [
            {
                "role": "user",
                "content": f"今天是 {today.isoformat()}，默认城市是{city}。用户请求：{cleaned_request}",
            }
        ]
        traces: list[ToolTrace] = []
        pending: list[dict[str, Any]] = []
        for _ in range(max_rounds):
            response = client.responses.create(
                model=model,
                instructions=(
                    "你是家庭洗晒助手。需要事实时主动调用工具，不得编造天气或物品记录。"
                    "如果用户请求安排、计划或建议，必须先分别调用 get_weather 和 "
                    "get_item_records，再结合降雨、湿度、晾晒适宜度与物品周期回答；"
                    "天气不适合时不得建议户外晾晒。"
                    "涉及完成任务的写入只能调用 complete_laundry_task 生成待确认动作，"
                    "不得声称已经写入。最终用简洁中文回答。"
                ),
                input=input_items,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                parallel_tool_calls=False,
                max_output_tokens=700,
                store=False,
            )
            calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
            if not calls:
                called_tools = {trace.name for trace in traces if trace.ok}
                if planning_request and not {
                    "get_weather",
                    "get_item_records",
                }.issubset(called_tools):
                    return _fallback(
                        repository,
                        weather,
                        today=today,
                        reason="Agent 未取得完整的天气和物品事实，已安全切换为规则计划。",
                    )
                answer = str(getattr(response, "output_text", "")).strip()
                if not answer:
                    raise ValueError("empty agent output")
                return AgentResult("AI Agent", answer, tuple(traces), tuple(pending))

            input_items.extend(response.output)
            for call in calls:
                try:
                    arguments = json.loads(call.arguments)
                except (TypeError, json.JSONDecodeError):
                    result = {"ok": False, "error": "工具参数不是有效 JSON。"}
                else:
                    result = registry.execute(call.name, arguments, allow_write=False)
                if action := result.get("pending_action"):
                    pending.append(action)
                traces.append(
                    ToolTrace(
                        call.name,
                        "已生成待确认操作" if result.get("requires_confirmation") else (
                            f"返回 {len(result.get('items', []))} 件物品"
                            if "items" in result
                            else ("查询成功" if result.get("ok") else str(result.get("error")))
                        ),
                        bool(result.get("ok")),
                    )
                )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
        return AgentResult(
            "AI Agent",
            "已达到工具调用上限，请缩小请求范围后重试。",
            tuple(traces),
            tuple(pending),
            fallback_reason="Agent 已安全停止，没有继续调用工具。",
        )
    except Exception as error:
        LOGGER.warning("Agent failed: %s", type(error).__name__)
        return _fallback(
            repository,
            weather,
            today=today,
            reason="模型或工具调用暂时不可用，已切换为规则建议。",
        )
