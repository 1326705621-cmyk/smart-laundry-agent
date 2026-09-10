"""通过参数化 SQL 提供物品数据的增删改查。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from smart_laundry.database import database_connection
from smart_laundry.models import (
    ActionType,
    ActivityRecord,
    Item,
    ItemNotFoundError,
    ItemValidationError,
    validate_item_input,
)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_item(row: object) -> Item:
    return Item(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        wash_interval_days=row["wash_interval_days"],
        dry_interval_days=row["dry_interval_days"],
        last_washed_at=row["last_washed_at"],
        last_dried_at=row["last_dried_at"],
        notes=row["notes"],
        image_path=row["image_path"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_activity(row: object) -> ActivityRecord:
    return ActivityRecord(
        id=row["id"],
        item_id=row["item_id"],
        action_type=row["action_type"],
        performed_at=row["performed_at"],
        source=row["source"],
        notes=row["notes"],
        created_at=row["created_at"],
    )


def _normalize_performed_at(value: date | datetime | str | None) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    try:
        datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ItemValidationError("完成日期格式无效。") from error
    return value


class ItemRepository:
    """物品数据访问入口，UI 不直接执行 SQL。"""

    def __init__(
        self,
        database_path: str | Path,
        *,
        owner_user_id: int | None = None,
        family_id: int | None = None,
    ) -> None:
        if owner_user_id is not None and family_id is not None:
            raise ValueError("个人空间和家庭空间不能同时作为物品范围。")
        self.database_path = Path(database_path)
        self.owner_user_id = owner_user_id
        self.family_id = family_id

    def _scope_sql(self, alias: str = "") -> tuple[str, tuple[int, ...]]:
        prefix = f"{alias}." if alias else ""
        if self.family_id is not None:
            return f"{prefix}family_id = ?", (self.family_id,)
        if self.owner_user_id is not None:
            return (
                f"{prefix}owner_user_id = ? AND {prefix}family_id IS NULL",
                (self.owner_user_id,),
            )
        return "1 = 1", ()

    def list_items(self) -> list[Item]:
        scope_sql, scope_parameters = self._scope_sql()
        with database_connection(self.database_path) as connection:
            rows = connection.execute(
                f"SELECT * FROM items WHERE {scope_sql} ORDER BY created_at DESC, id DESC",
                scope_parameters,
            ).fetchall()
        return [_row_to_item(row) for row in rows]

    def get_item(self, item_id: int) -> Item | None:
        scope_sql, scope_parameters = self._scope_sql()
        with database_connection(self.database_path) as connection:
            row = connection.execute(
                f"SELECT * FROM items WHERE id = ? AND {scope_sql}",
                (item_id, *scope_parameters),
            ).fetchone()
        return _row_to_item(row) if row is not None else None

    def find_by_name(self, name: str) -> Item | None:
        scope_sql, scope_parameters = self._scope_sql()
        with database_connection(self.database_path) as connection:
            row = connection.execute(
                f"""
                SELECT * FROM items
                WHERE lower(name) = lower(?) AND {scope_sql}
                ORDER BY id LIMIT 1
                """,
                (name.strip(), *scope_parameters),
            ).fetchone()
        return _row_to_item(row) if row is not None else None

    def create_item(
        self,
        *,
        name: str,
        category: str,
        wash_interval_days: int | None,
        dry_interval_days: int | None,
        notes: str = "",
        image_path: str | None = None,
    ) -> Item:
        item_input = validate_item_input(
            name=name,
            category=category,
            wash_interval_days=wash_interval_days,
            dry_interval_days=dry_interval_days,
            notes=notes,
            image_path=image_path,
        )
        now = _utc_now_text()
        with database_connection(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO items (
                    name, category, wash_interval_days, dry_interval_days,
                    last_washed_at, last_dried_at, notes, image_path,
                    owner_user_id, family_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_input.name,
                    item_input.category,
                    item_input.wash_interval_days,
                    item_input.dry_interval_days,
                    item_input.notes,
                    item_input.image_path,
                    self.owner_user_id,
                    self.family_id,
                    now,
                    now,
                ),
            )
            item_id = cursor.lastrowid
        item = self.get_item(int(item_id))
        if item is None:  # 防御性检查：正常 SQLite 写入不会进入此分支。
            raise RuntimeError("物品已写入，但无法重新读取。")
        return item

    def update_item(
        self,
        item_id: int,
        *,
        name: str,
        category: str,
        wash_interval_days: int | None,
        dry_interval_days: int | None,
        notes: str = "",
        image_path: str | None = None,
    ) -> Item:
        item_input = validate_item_input(
            name=name,
            category=category,
            wash_interval_days=wash_interval_days,
            dry_interval_days=dry_interval_days,
            notes=notes,
            image_path=image_path,
        )
        scope_sql, scope_parameters = self._scope_sql()
        with database_connection(self.database_path) as connection:
            cursor = connection.execute(
                f"""
                UPDATE items
                SET name = ?, category = ?, wash_interval_days = ?,
                    dry_interval_days = ?, notes = ?, image_path = ?, updated_at = ?
                WHERE id = ? AND {scope_sql}
                """,
                (
                    item_input.name,
                    item_input.category,
                    item_input.wash_interval_days,
                    item_input.dry_interval_days,
                    item_input.notes,
                    item_input.image_path,
                    _utc_now_text(),
                    item_id,
                    *scope_parameters,
                ),
            )
            if cursor.rowcount == 0:
                raise ItemNotFoundError(f"未找到 ID 为 {item_id} 的物品。")
        item = self.get_item(item_id)
        if item is None:
            raise RuntimeError("物品已更新，但无法重新读取。")
        return item

    def delete_item(self, item_id: int) -> bool:
        scope_sql, scope_parameters = self._scope_sql()
        with database_connection(self.database_path) as connection:
            cursor = connection.execute(
                f"DELETE FROM items WHERE id = ? AND {scope_sql}",
                (item_id, *scope_parameters),
            )
        return cursor.rowcount > 0

    def record_activity(
        self,
        item_id: int,
        action_type: ActionType,
        *,
        performed_at: date | datetime | str | None = None,
        source: str = "manual",
        notes: str = "",
    ) -> bool:
        """记录一次操作并同步最近日期；同一天重复提交不会重复写入。"""

        if action_type not in ("wash", "dry"):
            raise ItemValidationError("操作类型只能是 wash 或 dry。")
        if not source.strip() or len(source.strip()) > 40:
            raise ItemValidationError("记录来源格式无效。")
        cleaned_notes = notes.strip()
        if len(cleaned_notes) > 500:
            raise ItemValidationError("备注不能超过 500 个字符。")

        performed_text = _normalize_performed_at(performed_at)
        now = _utc_now_text()
        date_column = "last_washed_at" if action_type == "wash" else "last_dried_at"
        scope_sql, scope_parameters = self._scope_sql()

        with database_connection(self.database_path) as connection:
            exists = connection.execute(
                f"SELECT 1 FROM items WHERE id = ? AND {scope_sql}",
                (item_id, *scope_parameters),
            ).fetchone()
            if exists is None:
                raise ItemNotFoundError(f"未找到 ID 为 {item_id} 的物品。")

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO activity_records (
                    item_id, action_type, performed_at, source, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    action_type,
                    performed_text,
                    source.strip(),
                    cleaned_notes,
                    now,
                ),
            )
            if cursor.rowcount == 0:
                return False

            connection.execute(
                f"""
                UPDATE items
                SET {date_column} = CASE
                        WHEN {date_column} IS NULL OR {date_column} < ? THEN ?
                        ELSE {date_column}
                    END,
                    updated_at = ?
                WHERE id = ? AND {scope_sql}
                """,
                (performed_text, performed_text, now, item_id, *scope_parameters),
            )
        return True

    def list_activity_records(
        self, item_id: int, *, limit: int | None = None
    ) -> list[ActivityRecord]:
        """按时间倒序读取历史；页面可限制数量，完整历史仍保留在数据库。"""

        if limit is not None and (isinstance(limit, bool) or limit <= 0):
            raise ItemValidationError("历史记录数量必须是正整数。")
        scope_sql, scope_parameters = self._scope_sql("i")
        sql = f"""
            SELECT ar.* FROM activity_records AS ar
            JOIN items AS i ON i.id = ar.item_id
            WHERE ar.item_id = ? AND {scope_sql}
            ORDER BY ar.performed_at DESC, ar.id DESC
        """
        parameters: tuple[int, ...] = (item_id, *scope_parameters)
        if limit is not None:
            sql += " LIMIT ?"
            parameters = (*parameters, limit)
        with database_connection(self.database_path) as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [_row_to_activity(row) for row in rows]
