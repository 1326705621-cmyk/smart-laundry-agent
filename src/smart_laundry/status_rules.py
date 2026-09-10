"""根据日期和用户周期计算确定性的清洗、晾晒状态。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class ActionStatus:
    days_since: int | None
    ratio: float | None
    emoji: str
    label: str
    reason: str
    is_due: bool
    is_future_record: bool = False


def _to_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(value).date()


def calculate_action_status(
    last_performed_at: str | date | datetime | None,
    interval_days: int | None,
    *,
    today: date | None = None,
) -> ActionStatus:
    """按“已过天数 / 用户周期”计算状态，便于固定日期测试。"""

    if interval_days is not None and interval_days <= 0:
        raise ValueError("周期必须是正整数。")
    current_date = today or date.today()

    if interval_days is None:
        if last_performed_at is None:
            return ActionStatus(
                days_since=None,
                ratio=None,
                emoji="▫️",
                label="未设置周期",
                reason="未设置提醒周期，不参与到期提醒。",
                is_due=False,
            )
        raw_days = (current_date - _to_date(last_performed_at)).days
        if raw_days < 0:
            return ActionStatus(
                days_since=0,
                ratio=None,
                emoji="🙂",
                label="记录日期在未来",
                reason="最近记录晚于今天，请检查设备日期或记录日期。",
                is_due=False,
                is_future_record=True,
            )
        return ActionStatus(
            days_since=raw_days,
            ratio=None,
            emoji="▫️",
            label="未设置周期",
            reason=f"距离上次处理 {raw_days} 天；未设置周期，不参与到期提醒。",
            is_due=False,
        )

    if last_performed_at is None:
        return ActionStatus(
            days_since=None,
            ratio=None,
            emoji="❓",
            label="尚无记录",
            reason=f"还没有完成记录，建议确认是否需要处理（周期 {interval_days} 天）。",
            is_due=True,
        )

    performed_date = _to_date(last_performed_at)
    raw_days = (current_date - performed_date).days
    if raw_days < 0:
        return ActionStatus(
            days_since=0,
            ratio=0.0,
            emoji="🙂",
            label="记录日期在未来",
            reason="最近记录晚于今天，请检查设备日期或记录日期。",
            is_due=False,
            is_future_record=True,
        )

    ratio = raw_days / interval_days
    if ratio < 0.6:
        emoji, label = "😊", "状态良好"
    elif ratio < 1.0:
        emoji, label = "🙂", "快到建议时间"
    elif ratio < 1.5:
        emoji, label = "😐", "建议尽快处理"
    else:
        emoji, label = "😭", "已超期较久"

    remaining = interval_days - raw_days
    if remaining > 0:
        reason = f"距离上次处理 {raw_days} 天，约 {remaining} 天后到建议周期。"
    elif remaining == 0:
        reason = f"距离上次处理 {raw_days} 天，今天正好到建议周期。"
    else:
        reason = f"距离上次处理 {raw_days} 天，已超过建议周期 {abs(remaining)} 天。"

    return ActionStatus(
        days_since=raw_days,
        ratio=ratio,
        emoji=emoji,
        label=label,
        reason=reason,
        is_due=ratio >= 1.0,
    )


def elapsed_text(status: ActionStatus) -> str:
    if status.days_since is None:
        return "尚无记录"
    if status.days_since == 0:
        return "今天"
    return f"{status.days_since} 天"


def recorded_today(value: str | None, *, today: date | None = None) -> bool:
    if value is None:
        return False
    return _to_date(value) == (today or date.today())


def choose_item_emoji(
    wash_status: ActionStatus,
    dry_status: ActionStatus,
    *,
    is_sunny: bool,
) -> str:
    """晴天且任一动作到期时加强提醒，否则显示更紧急的基础表情。"""

    if is_sunny and (wash_status.is_due or dry_status.is_due):
        return "😠"
    statuses = (wash_status, dry_status)
    if all(status.ratio is None for status in statuses):
        return "🧺"
    return max(
        statuses,
        key=lambda status: 1.0 if status.days_since is None else (status.ratio or 0.0),
    ).emoji
