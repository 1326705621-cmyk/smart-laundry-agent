"""SQLite 连接和可重复执行的数据库初始化。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 80),
    category TEXT NOT NULL,
    wash_interval_days INTEGER CHECK (wash_interval_days IS NULL OR wash_interval_days BETWEEN 1 AND 3650),
    dry_interval_days INTEGER CHECK (dry_interval_days IS NULL OR dry_interval_days BETWEEN 1 AND 3650),
    last_washed_at TEXT,
    last_dried_at TEXT,
    notes TEXT NOT NULL DEFAULT '' CHECK (length(notes) <= 500),
    image_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

ACTIVITY_RECORDS_SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('wash', 'dry')),
    performed_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
    UNIQUE (item_id, action_type, performed_at)
);
"""

ACTIVITY_INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_activity_records_item_performed
ON activity_records (item_id, performed_at DESC);
"""

USER_ACCOUNTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identifier TEXT NOT NULL COLLATE NOCASE UNIQUE,
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) BETWEEN 1 AND 40),
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    preferred_city TEXT NOT NULL DEFAULT '' CHECK (length(preferred_city) <= 80),
    is_ui_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_ui_admin IN (0, 1)),
    created_at TEXT NOT NULL
);
"""

UI_ADMIN_INDEX_SCHEMA = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_single_ui_admin
ON user_accounts (is_ui_admin) WHERE is_ui_admin = 1;
"""

FAMILIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS families (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 40),
    join_code TEXT NOT NULL COLLATE NOCASE UNIQUE,
    created_by_user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (created_by_user_id) REFERENCES user_accounts(id) ON DELETE RESTRICT
);
"""

FAMILY_MEMBERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS family_members (
    family_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'member')),
    joined_at TEXT NOT NULL,
    PRIMARY KEY (family_id, user_id),
    FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES user_accounts(id) ON DELETE CASCADE
);
"""

APPEARANCE_PREFERENCES_SCHEMA = """
CREATE TABLE IF NOT EXISTS appearance_preferences (
    user_id INTEGER PRIMARY KEY,
    background_color TEXT NOT NULL,
    text_color TEXT NOT NULL,
    primary_color TEXT NOT NULL,
    reminder_color TEXT NOT NULL,
    clothing_color TEXT NOT NULL,
    bedding_color TEXT NOT NULL,
    toy_color TEXT NOT NULL,
    pet_color TEXT NOT NULL,
    font_family TEXT NOT NULL,
    font_scale INTEGER NOT NULL CHECK (font_scale BETWEEN 85 AND 120),
    card_radius INTEGER NOT NULL CHECK (card_radius BETWEEN 12 AND 32),
    spacing_scale INTEGER NOT NULL CHECK (spacing_scale BETWEEN 80 AND 125),
    shadow_strength INTEGER NOT NULL CHECK (shadow_strength BETWEEN 0 AND 30),
    page_size INTEGER NOT NULL CHECK (page_size BETWEEN 2 AND 5),
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES user_accounts(id) ON DELETE CASCADE
);
"""

VISUAL_DESIGNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS visual_designs (
    user_id INTEGER PRIMARY KEY,
    design_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES user_accounts(id) ON DELETE CASCADE
);
"""

ITEM_SCOPE_INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_items_scope
ON items (family_id, owner_user_id, created_at DESC);
"""


@contextmanager
def database_connection(database_path: str | Path) -> Iterator[sqlite3.Connection]:
    """打开短连接，并确保写入要么全部提交、要么全部回滚。"""

    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: str | Path) -> None:
    """创建缺失的数据表；重复调用不会清空已有数据。"""

    with database_connection(database_path) as connection:
        connection.execute(USER_ACCOUNTS_SCHEMA)
        account_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(user_accounts)").fetchall()
        }
        if "preferred_city" not in account_columns:
            connection.execute(
                "ALTER TABLE user_accounts ADD COLUMN preferred_city TEXT NOT NULL DEFAULT ''"
            )
        if "is_ui_admin" not in account_columns:
            connection.execute(
                "ALTER TABLE user_accounts ADD COLUMN is_ui_admin INTEGER NOT NULL DEFAULT 0"
            )
            connection.execute(
                """
                UPDATE user_accounts SET is_ui_admin = 1
                WHERE id = (SELECT MIN(id) FROM user_accounts)
                """
            )
        connection.execute(UI_ADMIN_INDEX_SCHEMA)
        connection.execute(FAMILIES_SCHEMA)
        connection.execute(FAMILY_MEMBERS_SCHEMA)
        connection.execute(APPEARANCE_PREFERENCES_SCHEMA)
        connection.execute(VISUAL_DESIGNS_SCHEMA)
        connection.execute(ITEMS_SCHEMA)
        column_info = connection.execute("PRAGMA table_info(items)").fetchall()
        item_columns = {row["name"] for row in column_info}
        if "image_path" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN image_path TEXT")
            column_info = connection.execute("PRAGMA table_info(items)").fetchall()
        interval_columns = {
            row["name"]: row["notnull"]
            for row in column_info
            if row["name"] in {"wash_interval_days", "dry_interval_days"}
        }
        if any(interval_columns.values()):
            _migrate_optional_intervals(connection)
            column_info = connection.execute("PRAGMA table_info(items)").fetchall()
            item_columns = {row["name"] for row in column_info}
        if "owner_user_id" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN owner_user_id INTEGER")
        if "family_id" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN family_id INTEGER")
        connection.execute(
            "UPDATE items SET category = '床上用品' WHERE category IN ('被褥', '其他')"
        )
        connection.execute(ACTIVITY_RECORDS_SCHEMA)
        connection.execute(ACTIVITY_INDEX_SCHEMA)
        connection.execute(ITEM_SCOPE_INDEX_SCHEMA)


def _migrate_optional_intervals(connection: sqlite3.Connection) -> None:
    """把旧版必填周期表迁移为可空字段，并保留物品主键。"""

    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("DROP TABLE IF EXISTS items_optional_intervals")
    connection.execute(ITEMS_SCHEMA.replace("items", "items_optional_intervals", 1))
    connection.execute(
        """
        INSERT INTO items_optional_intervals (
            id, name, category, wash_interval_days, dry_interval_days,
            last_washed_at, last_dried_at, notes, image_path, created_at, updated_at
        )
        SELECT id, name, category, wash_interval_days, dry_interval_days,
               last_washed_at, last_dried_at, notes, image_path, created_at, updated_at
        FROM items
        """
    )
    connection.execute("DROP TABLE items")
    connection.execute("ALTER TABLE items_optional_intervals RENAME TO items")
    connection.execute("PRAGMA foreign_keys = ON")
