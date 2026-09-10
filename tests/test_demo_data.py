from pathlib import Path

from smart_laundry.demo_data import DEMO_ITEMS, seed_demo_data
from smart_laundry.repositories import ItemRepository


def test_seed_demo_data_is_idempotent(database_path: Path) -> None:
    first_inserted = seed_demo_data(database_path)
    second_inserted = seed_demo_data(database_path)

    assert first_inserted == len(DEMO_ITEMS)
    assert second_inserted == 0
    assert len(ItemRepository(database_path).list_items()) == len(DEMO_ITEMS)
