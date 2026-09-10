from datetime import date
from pathlib import Path
import sqlite3

import pytest

from smart_laundry.models import ItemValidationError
from smart_laundry.repositories import ItemRepository


def _create_item(repository: ItemRepository):
    return repository.create_item(
        name="测试被子",
        category="被褥",
        wash_interval_days=30,
        dry_interval_days=14,
    )


def test_record_activity_updates_item_and_is_idempotent(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    item = _create_item(repository)
    performed = date(2026, 8, 29)

    assert repository.record_activity(item.id, "wash", performed_at=performed) is True
    assert repository.record_activity(item.id, "wash", performed_at=performed) is False

    updated = repository.get_item(item.id)
    records = repository.list_activity_records(item.id)
    assert updated is not None
    assert updated.last_washed_at == "2026-08-29"
    assert updated.last_dried_at is None
    assert len(records) == 1
    assert records[0].action_type == "wash"


def test_wash_and_dry_are_recorded_independently(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    item = _create_item(repository)

    repository.record_activity(item.id, "wash", performed_at="2026-08-28")
    repository.record_activity(item.id, "dry", performed_at="2026-08-29")

    updated = repository.get_item(item.id)
    assert updated is not None
    assert updated.last_washed_at == "2026-08-28"
    assert updated.last_dried_at == "2026-08-29"
    assert len(repository.list_activity_records(item.id)) == 2


def test_invalid_action_is_rejected(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    item = _create_item(repository)

    with pytest.raises(ItemValidationError, match="wash 或 dry"):
        repository.record_activity(item.id, "iron")


def test_deleting_item_cascades_to_activity_records(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    item = _create_item(repository)
    repository.record_activity(item.id, "wash", performed_at="2026-08-29")

    repository.delete_item(item.id)

    assert repository.list_activity_records(item.id) == []


def test_history_is_newest_first_and_can_be_limited(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    item = _create_item(repository)
    repository.record_activity(item.id, "wash", performed_at="2026-08-27")
    repository.record_activity(item.id, "dry", performed_at="2026-08-28")
    repository.record_activity(item.id, "wash", performed_at="2026-08-29")

    records = repository.list_activity_records(item.id, limit=2)

    assert [(record.performed_at, record.action_type) for record in records] == [
        ("2026-08-29", "wash"),
        ("2026-08-28", "dry"),
    ]


def test_activity_and_latest_date_roll_back_together(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    item = _create_item(repository)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_item_update
            BEFORE UPDATE ON items
            BEGIN
                SELECT RAISE(ABORT, 'simulated update failure');
            END;
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="simulated update failure"):
        repository.record_activity(item.id, "wash", performed_at="2026-08-29")

    unchanged = repository.get_item(item.id)
    assert unchanged is not None
    assert unchanged.last_washed_at is None
    assert repository.list_activity_records(item.id) == []


def test_invalid_history_limit_is_rejected(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    item = _create_item(repository)

    with pytest.raises(ItemValidationError, match="正整数"):
        repository.list_activity_records(item.id, limit=0)
