from pathlib import Path

import pytest

from smart_laundry.database import initialize_database


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    """每个测试使用独立的临时数据库，不接触开发数据。"""

    path = tmp_path / "test_smart_laundry.db"
    initialize_database(path)
    return path
