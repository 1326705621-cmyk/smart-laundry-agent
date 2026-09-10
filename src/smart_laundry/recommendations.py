"""确定性规则计划，以及可选 LLM 建议的结构化上下文。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from smart_laundry.models import Item
from smart_laundry.status_rules import calculate_action_status
from smart_laundry.weather import WeatherSummary


LOGGER = logging.getLogger(__name__)
Priority = Literal["高", "中", "低"]


@dataclass(frozen=True, slots=True)
class PlanTask:
    item_id: int
    item_name: str
    action: Literal["清洗", "晾晒", "暂缓洗晒", "暂缓晾晒"]
    priority: Priority
    reason: str


@dataclass(frozen=True, slots=True)
class RulePlan:
    summary: str
    tasks: tuple[PlanTask, ...]


@dataclass(frozen=True, slots=True)
class AdviceResult:
    mode: Literal["AI 建议", "规则建议"]
    text: str
    plan: RulePlan
    fallback_reason: str | None = None


def due_wash_item_names(items: list[Item], *, today: date) -> list[str]:
    """顶部只列真正到清洗周期、且今天尚未清洗的物品。"""

    names = []
    for item in items:
        status = calculate_action_status(item.last_washed_at, item.wash_interval_days, today=today)
        if status.is_due:
            names.append(item.name)
    return names


def _priority_from_ratio(ratio: float | None) -> Priority:
    if ratio is None or ratio >= 1.5:
        return "高"
    if ratio >= 1.0:
        return "中"
    return "低"


def build_rule_plan(
    items: list[Item],
    weather: WeatherSummary | None,
    *,
    today: date,
) -> RulePlan:
    tasks: list[PlanTask] = []
    suitable_for_drying = bool(weather and weather.is_suitable_for_drying)
    for item in items:
        wash = calculate_action_status(item.last_washed_at, item.wash_interval_days, today=today)
        dry = calculate_action_status(item.last_dried_at, item.dry_interval_days, today=today)

        if wash.is_due:
            if suitable_for_drying:
                action = "清洗"
                weather_note = "今天适合晾晒，可安排清洗后充分晾干。"
            else:
                action = "暂缓洗晒"
                weather_note = (
                    f"今天{weather.condition}、{weather.drying_label}，建议等天气转好。"
                    if weather
                    else "天气暂不可用，先不要安排户外洗晒。"
                )
            tasks.append(
                PlanTask(
                    item_id=item.id,
                    item_name=item.name,
                    action=action,
                    priority=_priority_from_ratio(wash.ratio),
                    reason=f"{wash.reason} {weather_note}",
                )
            )
        elif dry.is_due:
            action = "晾晒" if suitable_for_drying else "暂缓晾晒"
            weather_note = (
                "今日天气适合户外晾晒。"
                if suitable_for_drying
                else (
                    f"今天{weather.condition}、{weather.drying_label}，不安排户外晾晒。"
                    if weather
                    else "天气暂不可用，先不安排户外晾晒。"
                )
            )
            tasks.append(
                PlanTask(
                    item_id=item.id,
                    item_name=item.name,
                    action=action,
                    priority=_priority_from_ratio(dry.ratio),
                    reason=f"{dry.reason} {weather_note}",
                )
            )

    order = {"高": 0, "中": 1, "低": 2}
    tasks.sort(key=lambda task: (order[task.priority], task.item_id))
    if not tasks:
        summary = "今天没有必须处理的物品，保持通风并按自己的节奏安排即可。"
    elif all(task.action.startswith("暂缓") for task in tasks):
        summary = f"今天有 {len(tasks)} 项需要关注，但天气不适合户外洗晒，建议暂缓。"
    else:
        summary = f"今天建议安排 {len(tasks)} 项任务，先处理高优先级和已超期物品。"
    return RulePlan(summary=summary, tasks=tuple(tasks))


def render_rule_plan(plan: RulePlan) -> str:
    lines = [plan.summary]
    for index, task in enumerate(plan.tasks, start=1):
        lines.append(
            f"{index}. 【{task.priority}】{task.action}“{task.item_name}”：{task.reason}"
        )
    return "\n".join(lines)


def _plan_context(plan: RulePlan, weather: WeatherSummary | None, today: date) -> str:
    data = {
        "today": today.isoformat(),
        "weather": None
        if weather is None
        else {
            "condition": weather.condition,
            "rain_probability": weather.precipitation_probability,
            "humidity": weather.relative_humidity,
            "drying_label": weather.drying_label,
        },
        "rule_plan": {
            "summary": plan.summary,
            "tasks": [
                {
                    "item_id": task.item_id,
                    "item_name": task.item_name,
                    "action": task.action,
                    "priority": task.priority,
                    "reason": task.reason,
                }
                for task in plan.tasks
            ],
        },
    }
    return json.dumps(data, ensure_ascii=False)


def generate_advice(
    items: list[Item],
    weather: WeatherSummary | None,
    *,
    today: date,
    api_key: str | None,
    model: str | None,
    base_url: str | None = None,
    client: Any | None = None,
) -> AdviceResult:
    """优先尝试 LLM；缺配置或调用失败时返回同一份规则计划。"""

    plan = build_rule_plan(items, weather, today=today)
    rule_text = render_rule_plan(plan)
    if not api_key or not model:
        return AdviceResult(
            mode="规则建议",
            text=rule_text,
            plan=plan,
            fallback_reason="未配置 OPENAI_API_KEY 和 OPENAI_MODEL。",
        )

    try:
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url, timeout=20.0)
        response = client.responses.create(
            model=model,
            instructions=(
                "你是家庭洗晒助手。只依据提供的结构化事实，用中文输出简洁今日计划；"
                "保留任务优先级与物品名，不编造天气、记录或卫生结论。"
            ),
            input=_plan_context(plan, weather, today),
            max_output_tokens=600,
            store=False,
        )
        text = str(response.output_text).strip()
        if not text:
            raise ValueError("empty model output")
        return AdviceResult(mode="AI 建议", text=text, plan=plan)
    except Exception as error:  # 第三方 SDK 边界统一映射，规则结果仍可使用。
        LOGGER.warning("LLM advice failed: %s", type(error).__name__)
        return AdviceResult(
            mode="规则建议",
            text=rule_text,
            plan=plan,
            fallback_reason="模型服务暂时不可用，已自动切换为规则建议。",
        )
