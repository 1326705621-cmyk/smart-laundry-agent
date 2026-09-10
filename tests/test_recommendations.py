from datetime import date
from pathlib import Path
from types import SimpleNamespace

from smart_laundry.recommendations import (
    build_rule_plan,
    due_wash_item_names,
    generate_advice,
)
from smart_laundry.repositories import ItemRepository
from smart_laundry.weather import WeatherSummary


TODAY = date(2026, 8, 29)


def _weather() -> WeatherSummary:
    return WeatherSummary(
        city="北京",
        resolved_location="北京 · 中国",
        forecast_date="2026-08-29",
        condition="晴",
        weather_code=0,
        current_temperature=26,
        minimum_temperature=20,
        maximum_temperature=30,
        precipitation_probability=5,
        relative_humidity=50,
        wind_speed=8,
        is_sunny=True,
        is_suitable_for_drying=True,
        drying_label="适合户外晾晒",
        source="fixture",
        fetched_at="2026-08-29T08:00:00+00:00",
    )


def _rainy_weather() -> WeatherSummary:
    return WeatherSummary(
        city="北京",
        resolved_location="北京 · 中国",
        forecast_date="2026-08-29",
        condition="大雨",
        weather_code=65,
        current_temperature=22,
        minimum_temperature=19,
        maximum_temperature=24,
        precipitation_probability=95,
        relative_humidity=96,
        wind_speed=5,
        is_sunny=False,
        is_suitable_for_drying=False,
        drying_label="不建议户外晾晒",
        source="fixture",
        fetched_at="2026-08-29T08:00:00+00:00",
    )


def _items(database_path: Path):
    repository = ItemRepository(database_path)
    due = repository.create_item(
        name="到期被子", category="被褥", wash_interval_days=10, dry_interval_days=10
    )
    fresh = repository.create_item(
        name="刚洗床单", category="被褥", wash_interval_days=10, dry_interval_days=10
    )
    repository.record_activity(due.id, "wash", performed_at="2026-08-10")
    repository.record_activity(due.id, "dry", performed_at="2026-08-10")
    repository.record_activity(fresh.id, "wash", performed_at=TODAY)
    repository.record_activity(fresh.id, "dry", performed_at=TODAY)
    return repository.list_items()


def test_attention_names_only_include_due_wash_items(database_path: Path) -> None:
    items = _items(database_path)

    assert due_wash_item_names(items, today=TODAY) == ["到期被子"]


def test_rule_plan_orders_due_task(database_path: Path) -> None:
    plan = build_rule_plan(_items(database_path), _weather(), today=TODAY)

    assert plan.tasks[0].item_name == "到期被子"
    assert plan.tasks[0].action == "清洗"
    assert plan.tasks[0].priority == "高"


def test_rainy_day_defers_due_washing_and_drying(database_path: Path) -> None:
    plan = build_rule_plan(_items(database_path), _rainy_weather(), today=TODAY)

    assert plan.tasks[0].action == "暂缓洗晒"
    assert "大雨" in plan.tasks[0].reason
    assert "不适合户外洗晒" in plan.summary


def test_missing_key_uses_rule_mode(database_path: Path) -> None:
    result = generate_advice(
        _items(database_path), _weather(), today=TODAY, api_key=None, model=None
    )

    assert result.mode == "规则建议"
    assert "到期被子" in result.text


def test_fake_llm_client_returns_ai_advice(database_path: Path) -> None:
    class FakeResponses:
        def create(self, **kwargs):
            assert kwargs["store"] is False
            return SimpleNamespace(output_text="优先清洗到期被子，并利用晴天充分晾晒。")

    client = SimpleNamespace(responses=FakeResponses())
    result = generate_advice(
        _items(database_path),
        _weather(),
        today=TODAY,
        api_key="test-key",
        model="test-model",
        client=client,
    )

    assert result.mode == "AI 建议"
    assert "到期被子" in result.text


def test_llm_failure_falls_back_to_rules(database_path: Path) -> None:
    class FailingResponses:
        def create(self, **kwargs):
            raise TimeoutError("simulated")

    result = generate_advice(
        _items(database_path),
        _weather(),
        today=TODAY,
        api_key="test-key",
        model="test-model",
        client=SimpleNamespace(responses=FailingResponses()),
    )

    assert result.mode == "规则建议"
    assert result.fallback_reason is not None
