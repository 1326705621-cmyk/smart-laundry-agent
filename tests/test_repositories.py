from pathlib import Path

import pytest

from smart_laundry.models import ItemNotFoundError, ItemValidationError
from smart_laundry.repositories import ItemRepository


def test_create_and_list_items_persist_between_repository_instances(
    database_path: Path,
) -> None:
    repository = ItemRepository(database_path)
    created = repository.create_item(
        name="  主卧床单  ",
        category="被褥",
        wash_interval_days=14,
        dry_interval_days=7,
        notes="  周末处理  ",
    )

    reopened_repository = ItemRepository(database_path)
    items = reopened_repository.list_items()

    assert created.id > 0
    assert created.name == "主卧床单"
    assert created.notes == "周末处理"
    assert items == [created]


def test_update_item(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    created = repository.create_item(
        name="抱枕",
        category="其他",
        wash_interval_days=30,
        dry_interval_days=14,
    )

    updated = repository.update_item(
        created.id,
        name="沙发抱枕",
        category="其他",
        wash_interval_days=20,
        dry_interval_days=10,
        notes="低温清洗",
    )

    assert updated.name == "沙发抱枕"
    assert updated.wash_interval_days == 20
    assert updated.notes == "低温清洗"


def test_optional_intervals_can_be_left_blank(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    item = repository.create_item(
        name="纪念毛毯",
        category="被褥",
        wash_interval_days=None,
        dry_interval_days=None,
    )

    assert item.wash_interval_days is None
    assert item.dry_interval_days is None


def test_delete_item(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    created = repository.create_item(
        name="窗帘",
        category="其他",
        wash_interval_days=180,
        dry_interval_days=60,
    )

    assert repository.delete_item(created.id) is True
    assert repository.get_item(created.id) is None
    assert repository.delete_item(created.id) is False


def test_invalid_input_is_rejected_before_write(database_path: Path) -> None:
    repository = ItemRepository(database_path)

    with pytest.raises(ItemValidationError, match="名称不能为空"):
        repository.create_item(
            name="   ",
            category="其他",
            wash_interval_days=30,
            dry_interval_days=10,
        )

    with pytest.raises(ItemValidationError, match="必须在"):
        repository.create_item(
            name="测试物品",
            category="其他",
            wash_interval_days=0,
            dry_interval_days=10,
        )

    assert repository.list_items() == []


def test_parameterized_sql_keeps_name_as_plain_text(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    unusual_name = "衣物'); DROP TABLE items; --"

    created = repository.create_item(
        name=unusual_name,
        category="衣物",
        wash_interval_days=14,
        dry_interval_days=7,
    )

    assert created.name == unusual_name
    assert len(repository.list_items()) == 1


def test_updating_missing_item_reports_not_found(database_path: Path) -> None:
    repository = ItemRepository(database_path)

    with pytest.raises(ItemNotFoundError, match="未找到"):
        repository.update_item(
            999,
            name="不存在",
            category="其他",
            wash_interval_days=30,
            dry_interval_days=10,
        )
