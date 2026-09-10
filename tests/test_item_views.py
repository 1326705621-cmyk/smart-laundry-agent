from datetime import date
from pathlib import Path

from smart_laundry.item_views import filter_and_sort_items, search_items
from smart_laundry.repositories import ItemRepository


TODAY = date(2026, 8, 29)


def test_filter_sort_and_search(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    old = repository.create_item(
        name="主卧被子", category="床上用品", wash_interval_days=30, dry_interval_days=14,
        notes="蓝色"
    )
    recent = repository.create_item(
        name="客厅抱枕", category="衣物", wash_interval_days=30, dry_interval_days=None
    )
    repository.record_activity(old.id, "wash", performed_at="2026-07-01")
    repository.record_activity(recent.id, "wash", performed_at="2026-08-28")
    items = repository.list_items()

    ordered = filter_and_sort_items(
        items, action="wash", descending=True, category=None, today=TODAY
    )
    filtered = filter_and_sort_items(
        items, action="wash", descending=False, category="床上用品", today=TODAY
    )

    assert [item.name for item in ordered] == ["主卧被子", "客厅抱枕"]
    assert [item.name for item in filtered] == ["主卧被子"]
    assert [item.name for item in search_items(items, "蓝色")] == ["主卧被子"]
