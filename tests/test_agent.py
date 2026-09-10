from datetime import date
from pathlib import Path
from types import SimpleNamespace

from smart_laundry.agent import run_laundry_agent
from smart_laundry.repositories import ItemRepository
from smart_laundry.weather import WeatherSummary


TODAY = date(2026, 8, 29)


def _sunny_weather() -> WeatherSummary:
    return WeatherSummary(
        city="北京",
        resolved_location="北京 · 中国",
        forecast_date=TODAY.isoformat(),
        condition="晴",
        weather_code=0,
        current_temperature=28,
        minimum_temperature=20,
        maximum_temperature=30,
        precipitation_probability=5,
        relative_humidity=45,
        wind_speed=8,
        is_sunny=True,
        is_suitable_for_drying=True,
        drying_label="适合户外晾晒",
        source="fixture",
        fetched_at="2026-08-29T08:00:00+00:00",
    )


def test_agent_executes_read_tool_then_answers(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    repository.create_item(
        name="床单", category="被褥", wash_interval_days=10, dry_interval_days=7
    )

    class FakeResponses:
        count = 0

        def create(self, **kwargs):
            self.count += 1
            if self.count == 1:
                call = SimpleNamespace(
                    type="function_call",
                    name="get_weather",
                    arguments='{"city":"北京","days":1}',
                    call_id="call_1",
                )
                return SimpleNamespace(output=[call], output_text="")
            if self.count == 2:
                call = SimpleNamespace(
                    type="function_call",
                    name="get_item_records",
                    arguments='{"status_filter":"all"}',
                    call_id="call_2",
                )
                return SimpleNamespace(output=[call], output_text="")
            assert any(
                isinstance(item, dict) and item.get("type") == "function_call_output"
                for item in kwargs["input"]
            )
            return SimpleNamespace(output=[], output_text="今天先处理床单。")

    result = run_laundry_agent(
        "安排今天的洗晒",
        city="北京",
        repository=repository,
        weather=_sunny_weather(),
        today=TODAY,
        api_key="test-key",
        model="test-model",
        client=SimpleNamespace(responses=FakeResponses()),
    )

    assert result.mode == "AI Agent"
    assert [trace.name for trace in result.trace] == ["get_weather", "get_item_records"]
    assert "床单" in result.answer


def test_agent_without_model_uses_rule_mode(database_path: Path) -> None:
    result = run_laundry_agent(
        "安排今天的洗晒",
        city="北京",
        repository=ItemRepository(database_path),
        weather=None,
        today=TODAY,
        api_key=None,
        model=None,
    )

    assert result.mode == "规则建议"
    assert result.fallback_reason is not None
    assert "不会安排户外晾晒" in result.answer


def test_planning_agent_missing_weather_tool_falls_back(database_path: Path) -> None:
    repository = ItemRepository(database_path)

    class IncompleteResponses:
        count = 0

        def create(self, **kwargs):
            self.count += 1
            if self.count == 1:
                call = SimpleNamespace(
                    type="function_call",
                    name="get_item_records",
                    arguments='{"status_filter":"all"}',
                    call_id="items_only",
                )
                return SimpleNamespace(output=[call], output_text="")
            return SimpleNamespace(output=[], output_text="直接给出计划")

    result = run_laundry_agent(
        "帮我安排今天的计划",
        city="北京",
        repository=repository,
        weather=_sunny_weather(),
        today=TODAY,
        api_key="test-key",
        model="test-model",
        client=SimpleNamespace(responses=IncompleteResponses()),
    )

    assert result.mode == "规则建议"
    assert "未取得完整" in str(result.fallback_reason)


def test_agent_write_call_only_creates_pending_action(database_path: Path) -> None:
    repository = ItemRepository(database_path)
    item = repository.create_item(
        name="床罩", category="被褥", wash_interval_days=10, dry_interval_days=7
    )

    class FakeResponses:
        count = 0

        def create(self, **kwargs):
            self.count += 1
            if self.count == 1:
                call = SimpleNamespace(
                    type="function_call",
                    name="complete_laundry_task",
                    arguments=(
                        f'{{"item_id":{item.id},"action_type":"wash",'
                        '"performed_at":"2026-08-29"}'
                    ),
                    call_id="write_1",
                )
                return SimpleNamespace(output=[call], output_text="")
            return SimpleNamespace(output=[], output_text="请确认记录床罩已清洗。")

    result = run_laundry_agent(
        "记录床罩今天洗过了",
        city="北京",
        repository=repository,
        weather=None,
        today=TODAY,
        api_key="test-key",
        model="test-model",
        client=SimpleNamespace(responses=FakeResponses()),
    )

    assert result.pending_actions[0]["item_id"] == item.id
    assert repository.list_activity_records(item.id) == []
