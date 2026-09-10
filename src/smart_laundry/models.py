"""物品领域模型与进入数据层前的输入校验。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ITEM_CATEGORIES = ("衣物", "床上用品", "玩偶", "宠物用品")
CATEGORY_ALIASES = {"被褥": "床上用品", "其他": "床上用品"}
MIN_INTERVAL_DAYS = 1
MAX_INTERVAL_DAYS = 3650


class ItemValidationError(ValueError):
    """用户输入不满足物品规则。"""


class ItemNotFoundError(LookupError):
    """指定 ID 的物品不存在。"""


@dataclass(frozen=True, slots=True)
class ItemInput:
    """新增或编辑物品时，已经校验和清理过的数据。"""

    name: str
    category: str
    wash_interval_days: int | None
    dry_interval_days: int | None
    notes: str
    image_path: str | None


@dataclass(frozen=True, slots=True)
class Item:
    """从 SQLite 读取出的完整物品记录。"""

    id: int
    name: str
    category: str
    wash_interval_days: int | None
    dry_interval_days: int | None
    last_washed_at: str | None
    last_dried_at: str | None
    notes: str
    image_path: str | None
    created_at: str
    updated_at: str


ActionType = Literal["wash", "dry"]


@dataclass(frozen=True, slots=True)
class ActivityRecord:
    """一次已完成的清洗或晾晒记录。"""

    id: int
    item_id: int
    action_type: ActionType
    performed_at: str
    source: str
    notes: str
    created_at: str


def validate_item_input(
    *,
    name: str,
    category: str,
    wash_interval_days: int | None,
    dry_interval_days: int | None,
    notes: str = "",
    image_path: str | None = None,
) -> ItemInput:
    """清理并校验物品输入，防止无效数据进入数据库。"""

    cleaned_name = name.strip()
    if not cleaned_name:
        raise ItemValidationError("物品名称不能为空。")
    if len(cleaned_name) > 80:
        raise ItemValidationError("物品名称不能超过 80 个字符。")
    normalized_category = CATEGORY_ALIASES.get(category, category)
    if normalized_category not in ITEM_CATEGORIES:
        raise ItemValidationError("请选择有效的物品类别。")

    for label, value in (
        ("清洗周期", wash_interval_days),
        ("晾晒周期", dry_interval_days),
    ):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise ItemValidationError(f"{label}必须是整数天数。")
        if not MIN_INTERVAL_DAYS <= value <= MAX_INTERVAL_DAYS:
            raise ItemValidationError(
                f"{label}必须在 {MIN_INTERVAL_DAYS}–{MAX_INTERVAL_DAYS} 天之间。"
            )

    cleaned_notes = notes.strip()
    if len(cleaned_notes) > 500:
        raise ItemValidationError("备注不能超过 500 个字符。")
    if image_path is not None and len(image_path) > 500:
        raise ItemValidationError("图片路径过长。")

    return ItemInput(
        name=cleaned_name,
        category=normalized_category,
        wash_interval_days=wash_interval_days,
        dry_interval_days=dry_interval_days,
        notes=cleaned_notes,
        image_path=image_path,
    )


def parse_optional_interval(value: str, label: str) -> int | None:
    """把页面中的空白周期转成 None，其余内容校验为合理整数。"""

    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        interval = int(cleaned)
    except ValueError as error:
        raise ItemValidationError(f"{label}必须填写整数天数，或留空。") from error
    if not MIN_INTERVAL_DAYS <= interval <= MAX_INTERVAL_DAYS:
        raise ItemValidationError(
            f"{label}必须在 {MIN_INTERVAL_DAYS}–{MAX_INTERVAL_DAYS} 天之间，或留空。"
        )
    return interval
