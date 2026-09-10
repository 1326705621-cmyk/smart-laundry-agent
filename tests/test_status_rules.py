from datetime import date, datetime

import pytest

from smart_laundry.status_rules import (
    calculate_action_status,
    choose_item_emoji,
    elapsed_text,
    recorded_today,
)


TODAY = date(2026, 8, 29)


@pytest.mark.parametrize(
    ("last_date", "expected_label", "expected_due"),
    [
        (date(2026, 8, 25), "状态良好", False),
        (date(2026, 8, 23), "快到建议时间", False),
        (date(2026, 8, 19), "建议尽快处理", True),
        (date(2026, 8, 14), "已超期较久", True),
    ],
)
def test_status_ratio_boundaries(last_date, expected_label, expected_due) -> None:
    status = calculate_action_status(last_date, 10, today=TODAY)

    assert status.label == expected_label
    assert status.is_due is expected_due


def test_missing_record_is_due_and_explained() -> None:
    status = calculate_action_status(None, 30, today=TODAY)

    assert status.emoji == "❓"
    assert status.days_since is None
    assert status.is_due is True
    assert elapsed_text(status) == "尚无记录"


def test_future_record_is_not_reported_as_negative_days() -> None:
    status = calculate_action_status(date(2026, 8, 30), 10, today=TODAY)

    assert status.days_since == 0
    assert status.is_future_record is True
    assert status.is_due is False


def test_today_helpers_accept_iso_datetime() -> None:
    status = calculate_action_status("2026-08-29T08:30:00", 7, today=TODAY)

    assert elapsed_text(status) == "今天"
    assert recorded_today("2026-08-29T08:30:00", today=TODAY) is True
    assert recorded_today(datetime(2026, 8, 28, 23, 0).isoformat(), today=TODAY) is False


def test_sunny_due_item_uses_angry_reminder() -> None:
    due = calculate_action_status(date(2026, 8, 19), 10, today=TODAY)
    good = calculate_action_status(date(2026, 8, 28), 10, today=TODAY)

    assert choose_item_emoji(due, good, is_sunny=True) == "😠"
    assert choose_item_emoji(due, good, is_sunny=False) == "😐"


def test_unset_interval_never_becomes_due() -> None:
    status = calculate_action_status(date(2025, 1, 1), None, today=TODAY)

    assert status.days_since == 605
    assert status.label == "未设置周期"
    assert status.is_due is False
