"""物品状态列表的筛选与排序，和 Streamlit 页面解耦。"""

from __future__ import annotations

from datetime import date
from typing import Literal

from smart_laundry.models import Item
from smart_laundry.status_rules import calculate_action_status


SortAction = Literal["wash", "dry"]


def filter_and_sort_items(
    items: list[Item],
    *,
    action: SortAction,
    descending: bool,
    category: str | None,
    today: date,
) -> list[Item]:
    """按类别筛选，再按距上次操作天数排序；无记录固定排在末尾。"""

    filtered = [item for item in items if category is None or item.category == category]

    def sort_key(item: Item) -> tuple[bool, int]:
        last_at = item.last_washed_at if action == "wash" else item.last_dried_at
        interval = item.wash_interval_days if action == "wash" else item.dry_interval_days
        days_since = calculate_action_status(last_at, interval, today=today).days_since
        if days_since is None:
            return True, 0
        return False, -days_since if descending else days_since

    return sorted(filtered, key=sort_key)


def search_items(items: list[Item], query: str) -> list[Item]:
    """按名称、类别或备注进行不区分大小写的包含搜索。"""

    needle = query.strip().casefold()
    if not needle:
        return list(items)
    return [
        item
        for item in items
        if needle in f"{item.name} {item.category} {item.notes}".casefold()
    ]
