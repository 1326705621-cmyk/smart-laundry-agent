"""可安全重复执行的演示物品初始化。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from smart_laundry.database import initialize_database
from smart_laundry.repositories import ItemRepository


DEMO_ITEMS = (
    {
        "name": "主卧四季被",
        "category": "床上用品",
        "wash_interval_days": 90,
        "dry_interval_days": 30,
        "notes": "换季时重点检查",
        "wash_days_ago": 100,
        "dry_days_ago": 20,
    },
    {
        "name": "儿童毛绒熊",
        "category": "玩偶",
        "wash_interval_days": 45,
        "dry_interval_days": 14,
        "notes": "使用轻柔模式",
        "wash_days_ago": 40,
        "dry_days_ago": 15,
    },
    {
        "name": "客厅沙发垫",
        "category": "床上用品",
        "wash_interval_days": 30,
        "dry_interval_days": 14,
        "notes": "晴天时拆下外套晾晒",
        "wash_days_ago": 10,
        "dry_days_ago": 18,
    },
    {
        "name": "宠物睡垫",
        "category": "宠物用品",
        "wash_interval_days": 14,
        "dry_interval_days": 7,
        "notes": "与日常衣物分开处理",
        "wash_days_ago": 3,
        "dry_days_ago": 2,
    },
    {
        "name": "冬季羽绒服",
        "category": "衣物",
        "wash_interval_days": 120,
        "dry_interval_days": 30,
        "notes": "清洗前查看洗涤标签",
        "wash_days_ago": 200,
        "dry_days_ago": 45,
    },
)


def seed_demo_data(
    database_path: str | Path,
    *,
    owner_user_id: int | None = None,
    family_id: int | None = None,
) -> int:
    """补充缺失的演示物品，返回本次新增数量。"""

    initialize_database(database_path)
    repository = ItemRepository(
        database_path, owner_user_id=owner_user_id, family_id=family_id
    )
    inserted = 0
    for item_data in DEMO_ITEMS:
        if repository.find_by_name(item_data["name"]) is not None:
            continue
        create_data = {
            key: value
            for key, value in item_data.items()
            if key not in ("wash_days_ago", "dry_days_ago")
        }
        item = repository.create_item(**create_data)
        repository.record_activity(
            item.id,
            "wash",
            performed_at=date.today() - timedelta(days=item_data["wash_days_ago"]),
            source="seed",
        )
        repository.record_activity(
            item.id,
            "dry",
            performed_at=date.today() - timedelta(days=item_data["dry_days_ago"]),
            source="seed",
        )
        inserted += 1
    return inserted
