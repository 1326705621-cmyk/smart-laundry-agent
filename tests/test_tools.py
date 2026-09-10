from datetime import date
from pathlib import Path

from smart_laundry.repositories import ItemRepository
from smart_laundry.tools import LaundryToolRegistry


TODAY = date(2026, 8, 29)


def test_read_tool_filters_due_and_write_waits_for_confirmation(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    item = repository.create_item(
        name="床单", category="被褥", wash_interval_days=10, dry_interval_days=None
    )
    repository.record_activity(item.id, "wash", performed_at="2026-08-01")
    registry = LaundryToolRegistry(repository, today=TODAY)

    read_result = registry.execute("get_item_records", {"status_filter": "wash_due"})
    pending = registry.execute(
        "complete_laundry_task",
        {"item_id": item.id, "action_type": "wash", "performed_at": TODAY.isoformat()},
    )

    assert read_result["items"][0]["item_id"] == item.id
    assert pending["requires_confirmation"] is True
    assert repository.get_item(item.id).last_washed_at == "2026-08-01"

    confirmed = registry.execute(
        "complete_laundry_task",
        {"item_id": item.id, "action_type": "wash", "performed_at": TODAY.isoformat()},
        allow_write=True,
    )
    assert confirmed["recorded"] is True
    assert repository.get_item(item.id).last_washed_at == TODAY.isoformat()


def test_tool_rejects_unknown_and_invalid_arguments(database_path: Path) -> None:
    registry = LaundryToolRegistry(ItemRepository(database_path), today=TODAY)

    assert registry.execute("delete_everything", {})["ok"] is False
    assert registry.execute("get_item_records", {"status_filter": "invalid"})["ok"] is False


def test_confirmed_write_reports_duplicate_and_rejects_future_date(
    database_path: Path,
) -> None:
    repository = ItemRepository(database_path)
    item = repository.create_item(
        name="毛毯", category="被褥", wash_interval_days=20, dry_interval_days=10
    )
    registry = LaundryToolRegistry(repository, today=TODAY)
    arguments = {
        "item_id": item.id,
        "action_type": "dry",
        "performed_at": TODAY.isoformat(),
    }

    first = registry.execute("complete_laundry_task", arguments, allow_write=True)
    duplicate = registry.execute("complete_laundry_task", arguments, allow_write=True)
    future = registry.execute(
        "complete_laundry_task",
        {**arguments, "performed_at": "2026-08-30"},
        allow_write=True,
    )

    assert first["recorded"] is True
    assert duplicate["recorded"] is False
    assert duplicate["duplicate"] is True
    assert "没有重复写入" in duplicate["message"]
    assert future == {"ok": False, "error": "完成日期不能晚于今天。"}
