"""Agent 可调用的受控工具：只开放天气、物品读取与确认后的记录写入。"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from smart_laundry.repositories import ItemRepository
from smart_laundry.status_rules import calculate_action_status
from smart_laundry.weather import WeatherError, WeatherService


class WeatherToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: str = Field(min_length=1, max_length=80)
    days: int = Field(default=1, ge=1, le=1)


class ItemRecordsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status_filter: Literal["all", "due", "wash_due", "dry_due"] = "all"


class CompleteTaskArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: int = Field(gt=0)
    action_type: Literal["wash", "dry"]
    performed_at: date | None = None


TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "get_weather",
        "description": "查询指定城市今天的天气和户外晾晒适宜度。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名，例如杭州"},
                "days": {"type": "integer", "enum": [1]},
            },
            "required": ["city", "days"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_item_records",
        "description": "读取家庭物品的最近清洗、晾晒日期及到期状态。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["all", "due", "wash_due", "dry_due"],
                }
            },
            "required": ["status_filter"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "complete_laundry_task",
        "description": "记录物品已清洗或已晾晒。必须先让用户在页面明确确认。",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {"type": "integer", "minimum": 1},
                "action_type": {"type": "string", "enum": ["wash", "dry"]},
                "performed_at": {"type": ["string", "null"], "format": "date"},
            },
            "required": ["item_id", "action_type", "performed_at"],
            "additionalProperties": False,
        },
    },
]


class LaundryToolRegistry:
    """校验工具参数并把调用限制在项目已有服务内。"""

    def __init__(
        self,
        repository: ItemRepository,
        *,
        weather_service: WeatherService | None = None,
        today: date | None = None,
    ) -> None:
        self.repository = repository
        self.weather_service = weather_service or WeatherService()
        self.today = today or date.today()

    def execute(
        self, name: str, arguments: dict[str, Any], *, allow_write: bool = False
    ) -> dict[str, Any]:
        try:
            if name == "get_weather":
                args = WeatherToolArgs.model_validate(arguments)
                result = self.weather_service.get_today(args.city)
                return {"ok": True, "weather": asdict(result)}
            if name == "get_item_records":
                args = ItemRecordsArgs.model_validate(arguments)
                records = []
                for item in self.repository.list_items():
                    wash = calculate_action_status(
                        item.last_washed_at, item.wash_interval_days, today=self.today
                    )
                    dry = calculate_action_status(
                        item.last_dried_at, item.dry_interval_days, today=self.today
                    )
                    if args.status_filter == "due" and not (wash.is_due or dry.is_due):
                        continue
                    if args.status_filter == "wash_due" and not wash.is_due:
                        continue
                    if args.status_filter == "dry_due" and not dry.is_due:
                        continue
                    records.append(
                        {
                            "item_id": item.id,
                            "name": item.name,
                            "category": item.category,
                            "wash": {"days_since": wash.days_since, "due": wash.is_due},
                            "dry": {"days_since": dry.days_since, "due": dry.is_due},
                        }
                    )
                return {"ok": True, "items": records}
            if name == "complete_laundry_task":
                args = CompleteTaskArgs.model_validate(arguments)
                if args.performed_at and args.performed_at > self.today:
                    return {"ok": False, "error": "完成日期不能晚于今天。"}
                item = self.repository.get_item(args.item_id)
                if item is None:
                    return {"ok": False, "error": "未找到指定物品。"}
                action = "清洗" if args.action_type == "wash" else "晾晒"
                if not allow_write:
                    return {
                        "ok": True,
                        "requires_confirmation": True,
                        "pending_action": {
                            "item_id": args.item_id,
                            "item_name": item.name,
                            "action_type": args.action_type,
                            "action_label": action,
                            "performed_at": (args.performed_at or self.today).isoformat(),
                        },
                    }
                created = self.repository.record_activity(
                    args.item_id,
                    args.action_type,
                    performed_at=args.performed_at or self.today,
                    source="agent_confirmed",
                )
                return {
                    "ok": True,
                    "recorded": created,
                    "duplicate": not created,
                    "item_name": item.name,
                    "message": (
                        f"已记录“{item.name}”完成{action}。"
                        if created
                        else f"“{item.name}”当天的{action}记录已经存在，没有重复写入。"
                    ),
                }
            return {"ok": False, "error": f"不支持的工具：{name}"}
        except ValidationError as error:
            return {"ok": False, "error": "工具参数无效。", "details": error.errors()}
        except WeatherError as error:
            return {"ok": False, "error": str(error)}
        except Exception as error:
            return {"ok": False, "error": f"工具执行失败：{type(error).__name__}"}
