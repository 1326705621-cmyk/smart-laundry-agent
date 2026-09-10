import sqlite3
from pathlib import Path

from smart_laundry.database import initialize_database


def test_initialize_database_is_repeatable(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "laundry.db"

    initialize_database(database_path)
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'items'"
        ).fetchone()

    assert table == ("items",)


def test_database_rejects_invalid_interval(database_path: Path) -> None:
    with sqlite3.connect(database_path) as connection:
        try:
            connection.execute(
                """
                INSERT INTO items (
                    name, category, wash_interval_days, dry_interval_days,
                    notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("测试物品", "其他", 0, 10, "", "2026-01-01", "2026-01-01"),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("数据库约束应拒绝 0 天周期")


def test_initialize_adds_image_column_to_older_database(tmp_path: Path) -> None:
    database_path = tmp_path / "old.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                wash_interval_days INTEGER NOT NULL,
                dry_interval_days INTEGER NOT NULL,
                last_washed_at TEXT,
                last_dried_at TEXT,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(items)")}
    assert "image_path" in columns


def test_old_required_intervals_migrate_and_keep_activity(tmp_path: Path) -> None:
    database_path = tmp_path / "old_with_activity.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                category TEXT NOT NULL, wash_interval_days INTEGER NOT NULL,
                dry_interval_days INTEGER NOT NULL, last_washed_at TEXT,
                last_dried_at TEXT, notes TEXT NOT NULL DEFAULT '', image_path TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE activity_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL,
                action_type TEXT NOT NULL, performed_at TEXT NOT NULL,
                source TEXT NOT NULL, notes TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
                UNIQUE (item_id, action_type, performed_at)
            );
            INSERT INTO items VALUES
                (1, '旧被子', '被褥', 30, 14, '2026-08-01', NULL, '', NULL, 'x', 'x');
            INSERT INTO activity_records VALUES
                (1, 1, 'wash', '2026-08-01', 'seed', '', 'x');
            """
        )

    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        info = {row[1]: row[3] for row in connection.execute("PRAGMA table_info(items)")}
        activity = connection.execute(
            "SELECT item_id, action_type FROM activity_records"
        ).fetchone()
        connection.execute(
            "UPDATE items SET wash_interval_days = NULL, dry_interval_days = NULL WHERE id = 1"
        )
    assert info["wash_interval_days"] == 0
    assert info["dry_interval_days"] == 0
    assert activity == (1, "wash")
