"""本地账户、家庭码和家庭成员关系。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from smart_laundry.database import database_connection
from smart_laundry.visual_design import DEFAULT_VISUAL_DESIGN, validate_visual_design


PASSWORD_ITERATIONS = 240_000
FAMILY_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^\+?\d{6,20}$")
HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
FONT_FAMILIES = ("Arial + 黑体", "Arial + 微软雅黑", "系统默认")


class AccountError(ValueError):
    """账户或家庭操作不满足业务规则。"""


@dataclass(frozen=True, slots=True)
class UserAccount:
    id: int
    identifier: str
    display_name: str
    preferred_city: str
    is_ui_admin: bool
    created_at: str


@dataclass(frozen=True, slots=True)
class Family:
    id: int
    name: str
    join_code: str
    role: str
    created_at: str


@dataclass(frozen=True, slots=True)
class AppearancePreferences:
    """一个账户的网页外观偏好；默认值与现有设计保持一致。"""

    background_color: str = "#FFFFFF"
    text_color: str = "#17263F"
    primary_color: str = "#7777DA"
    reminder_color: str = "#E96A87"
    clothing_color: str = "#399D8C"
    bedding_color: str = "#666BD0"
    toy_color: str = "#CE5370"
    pet_color: str = "#765BD0"
    font_family: str = "Arial + 黑体"
    font_scale: int = 100
    card_radius: int = 22
    spacing_scale: int = 100
    shadow_strength: int = 10
    page_size: int = 4


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_identifier(identifier: str) -> str:
    cleaned = identifier.strip().casefold()
    if not (EMAIL_PATTERN.fullmatch(cleaned) or PHONE_PATTERN.fullmatch(cleaned)):
        raise AccountError("请输入有效的邮箱或手机号。")
    return cleaned


def _validate_password(password: str) -> None:
    if not 8 <= len(password) <= 128:
        raise AccountError("密码长度需要为 8–128 个字符。")


def _password_digest(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return base64.b64encode(digest).decode("ascii")


def _row_to_user(row: object) -> UserAccount:
    return UserAccount(
        id=row["id"],
        identifier=row["identifier"],
        display_name=row["display_name"],
        preferred_city=row["preferred_city"],
        is_ui_admin=bool(row["is_ui_admin"]),
        created_at=row["created_at"],
    )


class AccountRepository:
    """管理本地登录与共享家庭；不依赖第三方账号服务。"""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def get_user(self, user_id: int) -> UserAccount | None:
        with database_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT id, identifier, display_name, preferred_city, is_ui_admin, created_at
                FROM user_accounts WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        return _row_to_user(row) if row else None

    def get_ui_admin(self) -> UserAccount | None:
        """返回唯一页面管理员；普通用户只消费其发布后的页面设计。"""

        with database_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT id, identifier, display_name, preferred_city, is_ui_admin, created_at
                FROM user_accounts WHERE is_ui_admin = 1 LIMIT 1
                """
            ).fetchone()
        return _row_to_user(row) if row else None

    def update_preferred_city(self, user_id: int, city: str) -> UserAccount:
        """保存账户常住城市，让刷新、退出登录后仍能恢复选择。"""

        cleaned_city = city.strip()
        if not 1 <= len(cleaned_city) <= 80:
            raise AccountError("城市名称需要为 1–80 个字符。")
        with database_connection(self.database_path) as connection:
            cursor = connection.execute(
                "UPDATE user_accounts SET preferred_city = ? WHERE id = ?",
                (cleaned_city, user_id),
            )
            if cursor.rowcount != 1:
                raise AccountError("账户不存在，请重新登录。")
        user = self.get_user(user_id)
        if user is None:
            raise AccountError("账户不存在，请重新登录。")
        return user

    def get_appearance_preferences(self, user_id: int) -> AppearancePreferences:
        """读取账户主题；尚未设置时返回不会写库的默认主题。"""

        with database_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM appearance_preferences WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return AppearancePreferences()
        return AppearancePreferences(
            background_color=row["background_color"],
            text_color=row["text_color"],
            primary_color=row["primary_color"],
            reminder_color=row["reminder_color"],
            clothing_color=row["clothing_color"],
            bedding_color=row["bedding_color"],
            toy_color=row["toy_color"],
            pet_color=row["pet_color"],
            font_family=row["font_family"],
            font_scale=row["font_scale"],
            card_radius=row["card_radius"],
            spacing_scale=row["spacing_scale"],
            shadow_strength=row["shadow_strength"],
            page_size=row["page_size"],
        )

    def get_site_appearance_preferences(self) -> AppearancePreferences:
        """所有访客看到管理员发布后的主题，但没有编辑权限。"""

        admin = self.get_ui_admin()
        return self.get_appearance_preferences(admin.id) if admin else AppearancePreferences()

    def update_appearance_preferences(
        self, user_id: int, preferences: AppearancePreferences
    ) -> AppearancePreferences:
        """校验并保存外观设置，避免无效 CSS 进入页面。"""

        color_values = (
            preferences.background_color,
            preferences.text_color,
            preferences.primary_color,
            preferences.reminder_color,
            preferences.clothing_color,
            preferences.bedding_color,
            preferences.toy_color,
            preferences.pet_color,
        )
        if any(not HEX_COLOR_PATTERN.fullmatch(value) for value in color_values):
            raise AccountError("颜色值格式不正确，请重新选择颜色。")
        if preferences.font_family not in FONT_FAMILIES:
            raise AccountError("请选择支持的字体组合。")
        if not 85 <= preferences.font_scale <= 120:
            raise AccountError("字号比例需要在 85%–120% 之间。")
        if not 12 <= preferences.card_radius <= 32:
            raise AccountError("卡片圆角需要在 12–32 之间。")
        if not 80 <= preferences.spacing_scale <= 125:
            raise AccountError("页面间距需要在 80%–125% 之间。")
        if not 0 <= preferences.shadow_strength <= 30:
            raise AccountError("阴影强度需要在 0–30 之间。")
        if not 2 <= preferences.page_size <= 5:
            raise AccountError("每页物品数量需要在 2–5 之间。")
        self._require_ui_admin(user_id)

        values = (
            user_id,
            *color_values,
            preferences.font_family,
            preferences.font_scale,
            preferences.card_radius,
            preferences.spacing_scale,
            preferences.shadow_strength,
            preferences.page_size,
            _utc_now_text(),
        )
        with database_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO appearance_preferences (
                    user_id, background_color, text_color, primary_color,
                    reminder_color, clothing_color, bedding_color, toy_color,
                    pet_color, font_family, font_scale, card_radius,
                    spacing_scale, shadow_strength, page_size, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    background_color=excluded.background_color,
                    text_color=excluded.text_color,
                    primary_color=excluded.primary_color,
                    reminder_color=excluded.reminder_color,
                    clothing_color=excluded.clothing_color,
                    bedding_color=excluded.bedding_color,
                    toy_color=excluded.toy_color,
                    pet_color=excluded.pet_color,
                    font_family=excluded.font_family,
                    font_scale=excluded.font_scale,
                    card_radius=excluded.card_radius,
                    spacing_scale=excluded.spacing_scale,
                    shadow_strength=excluded.shadow_strength,
                    page_size=excluded.page_size,
                    updated_at=excluded.updated_at
                """,
                values,
            )
        return self.get_appearance_preferences(user_id)

    def reset_appearance_preferences(self, user_id: int) -> AppearancePreferences:
        """删除自定义值并恢复项目默认主题。"""

        self._require_ui_admin(user_id)

        with database_connection(self.database_path) as connection:
            connection.execute(
                "DELETE FROM appearance_preferences WHERE user_id = ?", (user_id,)
            )
        return AppearancePreferences()

    def get_visual_design(self, user_id: int) -> dict:
        """读取高级设计画布；未保存时返回一份独立的默认布局。"""

        with database_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT design_json FROM visual_designs WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return json.loads(json.dumps(DEFAULT_VISUAL_DESIGN))
        try:
            return validate_visual_design(json.loads(row["design_json"]))
        except (json.JSONDecodeError, ValueError, TypeError):
            return json.loads(json.dumps(DEFAULT_VISUAL_DESIGN))

    def get_site_visual_design(self) -> dict:
        admin = self.get_ui_admin()
        if admin is None:
            return json.loads(json.dumps(DEFAULT_VISUAL_DESIGN))
        return self.get_visual_design(admin.id)

    def update_visual_design(self, user_id: int, design: object) -> dict:
        """验证并保存可视化布局；数据库中只保留安全的结构化参数。"""

        self._require_ui_admin(user_id)
        try:
            validated = validate_visual_design(design)
        except (ValueError, TypeError) as error:
            raise AccountError(str(error)) from error
        with database_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO visual_designs (user_id, design_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    design_json=excluded.design_json,
                    updated_at=excluded.updated_at
                """,
                (
                    user_id,
                    json.dumps(validated, ensure_ascii=False, separators=(",", ":")),
                    _utc_now_text(),
                ),
            )
        return validated

    def reset_visual_design(self, user_id: int) -> dict:
        self._require_ui_admin(user_id)
        with database_connection(self.database_path) as connection:
            connection.execute("DELETE FROM visual_designs WHERE user_id = ?", (user_id,))
        return json.loads(json.dumps(DEFAULT_VISUAL_DESIGN))

    def _require_ui_admin(self, user_id: int) -> UserAccount:
        """外观写操作的服务端权限门槛，不能只依赖隐藏按钮。"""

        user = self.get_user(user_id)
        if user is None:
            raise AccountError("账户不存在，请重新登录。")
        if not user.is_ui_admin:
            raise AccountError("只有页面管理员可以修改外观。")
        return user

    def register(
        self, identifier: str, password: str, *, display_name: str = ""
    ) -> UserAccount:
        cleaned_identifier = _normalize_identifier(identifier)
        _validate_password(password)
        cleaned_name = display_name.strip()
        if not cleaned_name:
            cleaned_name = (
                cleaned_identifier.split("@", 1)[0]
                if "@" in cleaned_identifier
                else f"用户{cleaned_identifier[-4:]}"
            )
        if not 1 <= len(cleaned_name) <= 40:
            raise AccountError("昵称需要为 1–40 个字符。")

        salt = secrets.token_bytes(16)
        now = _utc_now_text()
        with database_connection(self.database_path) as connection:
            first_user = (
                connection.execute("SELECT COUNT(*) FROM user_accounts").fetchone()[0]
                == 0
            )
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO user_accounts (
                        identifier, display_name, password_salt, password_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        cleaned_identifier,
                        cleaned_name,
                        base64.b64encode(salt).decode("ascii"),
                        _password_digest(password, salt),
                        now,
                    ),
                )
            except sqlite3.IntegrityError as error:
                if "UNIQUE constraint failed" in str(error):
                    raise AccountError("该邮箱或手机号已经注册。") from error
                raise
            user_id = int(cursor.lastrowid)
            if first_user:
                connection.execute(
                    "UPDATE user_accounts SET is_ui_admin = 1 WHERE id = ?",
                    (user_id,),
                )
                connection.execute(
                    """
                    UPDATE items SET owner_user_id = ?
                    WHERE owner_user_id IS NULL AND family_id IS NULL
                    """,
                    (user_id,),
                )
        user = self.get_user(user_id)
        if user is None:
            raise RuntimeError("账户已创建，但无法重新读取。")
        return user

    def authenticate(self, identifier: str, password: str) -> UserAccount:
        cleaned_identifier = _normalize_identifier(identifier)
        with database_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM user_accounts WHERE identifier = ?",
                (cleaned_identifier,),
            ).fetchone()
        if row is None:
            raise AccountError("账户或密码不正确。")
        salt = base64.b64decode(row["password_salt"])
        actual = _password_digest(password, salt)
        if not hmac.compare_digest(actual, row["password_hash"]):
            raise AccountError("账户或密码不正确。")
        return _row_to_user(row)

    def list_families(self, user_id: int) -> list[Family]:
        with database_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT f.id, f.name, f.join_code, fm.role, f.created_at
                FROM families AS f
                JOIN family_members AS fm ON fm.family_id = f.id
                WHERE fm.user_id = ?
                ORDER BY f.created_at, f.id
                """,
                (user_id,),
            ).fetchall()
        return [
            Family(
                id=row["id"],
                name=row["name"],
                join_code=row["join_code"],
                role=row["role"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def create_family(self, user_id: int, name: str) -> Family:
        cleaned_name = name.strip()
        if not 1 <= len(cleaned_name) <= 40:
            raise AccountError("家庭名称需要为 1–40 个字符。")
        if self.get_user(user_id) is None:
            raise AccountError("账户不存在，请重新登录。")

        now = _utc_now_text()
        with database_connection(self.database_path) as connection:
            for _ in range(20):
                join_code = "".join(
                    secrets.choice(FAMILY_CODE_ALPHABET) for _ in range(8)
                )
                if connection.execute(
                    "SELECT 1 FROM families WHERE join_code = ?", (join_code,)
                ).fetchone() is None:
                    break
            else:
                raise RuntimeError("暂时无法生成唯一家庭码，请稍后重试。")
            cursor = connection.execute(
                """
                INSERT INTO families (name, join_code, created_by_user_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (cleaned_name, join_code, user_id, now),
            )
            family_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO family_members (family_id, user_id, role, joined_at)
                VALUES (?, ?, 'owner', ?)
                """,
                (family_id, user_id, now),
            )
        return next(family for family in self.list_families(user_id) if family.id == family_id)

    def join_family(self, user_id: int, join_code: str) -> Family:
        cleaned_code = join_code.strip().upper().replace(" ", "")
        if not cleaned_code:
            raise AccountError("请输入家庭码。")
        with database_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT id FROM families WHERE join_code = ?", (cleaned_code,)
            ).fetchone()
            if row is None:
                raise AccountError("没有找到这个家庭码，请检查后重试。")
            family_id = int(row["id"])
            connection.execute(
                """
                INSERT OR IGNORE INTO family_members (family_id, user_id, role, joined_at)
                VALUES (?, ?, 'member', ?)
                """,
                (family_id, user_id, _utc_now_text()),
            )
        return next(family for family in self.list_families(user_id) if family.id == family_id)

    def user_can_access_family(self, user_id: int, family_id: int) -> bool:
        with database_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT 1 FROM family_members WHERE user_id = ? AND family_id = ?",
                (user_id, family_id),
            ).fetchone()
        return row is not None
