from pathlib import Path

import pytest

from smart_laundry.accounts import (
    AccountError,
    AccountRepository,
    AppearancePreferences,
)
from smart_laundry.repositories import ItemRepository


def test_register_authenticate_and_reject_duplicate(database_path: Path) -> None:
    accounts = AccountRepository(database_path)
    user = accounts.register("User@Example.com", "safe-pass-123", display_name="小雨")

    authenticated = accounts.authenticate("user@example.com", "safe-pass-123")

    assert authenticated == user
    assert authenticated.display_name == "小雨"
    with pytest.raises(AccountError, match="已经注册"):
        accounts.register("USER@example.com", "another-pass-123")
    with pytest.raises(AccountError, match="不正确"):
        accounts.authenticate("user@example.com", "wrong-pass")


def test_identifier_and_password_validation(database_path: Path) -> None:
    accounts = AccountRepository(database_path)

    with pytest.raises(AccountError, match="邮箱或手机号"):
        accounts.register("not-an-account", "safe-pass-123")
    with pytest.raises(AccountError, match="8–128"):
        accounts.register("user@example.com", "short")


def test_preferred_city_persists_for_account(database_path: Path) -> None:
    accounts = AccountRepository(database_path)
    user = accounts.register("city@example.com", "safe-pass-123")

    updated = accounts.update_preferred_city(user.id, " 广州 ")

    assert updated.preferred_city == "广州"
    assert accounts.get_user(user.id).preferred_city == "广州"
    assert accounts.authenticate("city@example.com", "safe-pass-123").preferred_city == "广州"
    with pytest.raises(AccountError, match="1–80"):
        accounts.update_preferred_city(user.id, " ")


def test_appearance_preferences_persist_and_reset(database_path: Path) -> None:
    accounts = AccountRepository(database_path)
    user = accounts.register("theme@example.com", "safe-pass-123")
    viewer = accounts.register("viewer@example.com", "safe-pass-456")
    custom = AppearancePreferences(
        background_color="#FAFBFF",
        primary_color="#315A9A",
        clothing_color="#4D8B7D",
        page_size=3,
        card_radius=28,
    )

    saved = accounts.update_appearance_preferences(user.id, custom)

    assert saved == custom
    assert accounts.get_appearance_preferences(user.id).page_size == 3
    assert accounts.get_site_appearance_preferences().page_size == 3
    assert user.is_ui_admin is True
    assert viewer.is_ui_admin is False
    with pytest.raises(AccountError, match="页面管理员"):
        accounts.update_appearance_preferences(viewer.id, custom)
    assert accounts.reset_appearance_preferences(user.id) == AppearancePreferences()


def test_appearance_preferences_reject_invalid_values(database_path: Path) -> None:
    accounts = AccountRepository(database_path)
    user = accounts.register("invalid-theme@example.com", "safe-pass-123")

    with pytest.raises(AccountError, match="颜色值"):
        accounts.update_appearance_preferences(
            user.id, AppearancePreferences(primary_color="blue")
        )
    with pytest.raises(AccountError, match="2–5"):
        accounts.update_appearance_preferences(
            user.id, AppearancePreferences(page_size=8)
        )


def test_visual_design_persists_and_resets(database_path: Path) -> None:
    accounts = AccountRepository(database_path)
    user = accounts.register("designer@example.com", "safe-pass-123")
    viewer = accounts.register("design-viewer@example.com", "safe-pass-456")
    design = accounts.get_visual_design(user.id)
    design["elements"][0]["x"] = 120
    design["elements"][0]["fill_type"] = "glass"
    design["elements"][0]["blur"] = 18
    design["elements"][0]["color1"] = "#AABBCC"

    saved = accounts.update_visual_design(user.id, design)

    assert saved["elements"][0]["x"] == 0
    assert accounts.get_visual_design(user.id)["elements"][0]["blur"] == 18
    assert accounts.get_site_visual_design()["elements"][0]["color1"] == "#AABBCC"
    with pytest.raises(AccountError, match="页面管理员"):
        accounts.update_visual_design(viewer.id, design)
    assert accounts.reset_visual_design(user.id)["elements"][0]["x"] == 0


def test_first_account_claims_legacy_items(database_path: Path) -> None:
    legacy = ItemRepository(database_path).create_item(
        name="旧物品",
        category="床上用品",
        wash_interval_days=30,
        dry_interval_days=14,
    )
    accounts = AccountRepository(database_path)
    first = accounts.register("first@example.com", "safe-pass-123")
    second = accounts.register("second@example.com", "safe-pass-456")

    assert ItemRepository(database_path, owner_user_id=first.id).get_item(legacy.id)
    assert ItemRepository(database_path, owner_user_id=second.id).list_items() == []


def test_family_code_shares_items_but_personal_spaces_stay_isolated(
    database_path: Path,
) -> None:
    accounts = AccountRepository(database_path)
    owner = accounts.register("owner@example.com", "safe-pass-123")
    member = accounts.register("member@example.com", "safe-pass-456")
    family = accounts.create_family(owner.id, "幸福小家")
    joined = accounts.join_family(member.id, family.join_code.lower())

    family_repository = ItemRepository(database_path, family_id=family.id)
    shared_item = family_repository.create_item(
        name="家庭公用毛毯",
        category="床上用品",
        wash_interval_days=30,
        dry_interval_days=14,
    )

    assert joined.id == family.id
    assert [item.id for item in ItemRepository(database_path, family_id=joined.id).list_items()] == [
        shared_item.id
    ]
    assert ItemRepository(database_path, owner_user_id=owner.id).get_item(shared_item.id) is None
    assert ItemRepository(database_path, owner_user_id=member.id).get_item(shared_item.id) is None
    with pytest.raises(AccountError, match="没有找到"):
        accounts.join_family(member.id, "INVALID1")
