from typing import Any

import pytest
import requests

from smart_laundry.weather import (
    FORECAST_URL,
    GEOCODING_URL,
    REVERSE_GEOCODING_URL,
    WeatherError,
    WeatherService,
    compact_weather_label,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(self, payloads: dict[str, dict[str, Any]]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, dict[str, Any], float]] = []

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any],
        timeout: float,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        self.calls.append((url, params, timeout))
        return FakeResponse(self.payloads[url])


def _sunny_payloads() -> dict[str, dict[str, Any]]:
    return {
        GEOCODING_URL: {
            "results": [
                {
                    "name": "北京",
                    "admin1": "北京市",
                    "country": "中国",
                    "latitude": 39.9,
                    "longitude": 116.4,
                }
            ]
        },
        FORECAST_URL: {
            "current": {
                "temperature_2m": 26.5,
                "relative_humidity_2m": 45,
                "weather_code": 0,
                "wind_speed_10m": 8.2,
            },
            "daily": {
                "time": ["2026-08-29"],
                "weather_code": [0],
                "temperature_2m_max": [30.0],
                "temperature_2m_min": [20.0],
                "precipitation_probability_max": [10],
            },
        },
    }


def test_weather_response_is_converted_to_internal_model() -> None:
    session = FakeSession(_sunny_payloads())

    weather = WeatherService(session=session, timeout=3).get_today(" 北京 ")

    assert weather.city == "北京"
    assert weather.condition == "晴"
    assert weather.is_sunny is True
    assert weather.is_suitable_for_drying is True
    assert weather.precipitation_probability == 10
    assert [call[0] for call in session.calls] == [GEOCODING_URL, FORECAST_URL]
    assert session.calls[1][1]["forecast_days"] == 1


def test_unknown_city_has_friendly_error() -> None:
    session = FakeSession({GEOCODING_URL: {"results": []}})

    with pytest.raises(WeatherError, match="没有找到"):
        WeatherService(session=session).get_today("不存在的城市")


def test_coordinates_are_resolved_to_city() -> None:
    session = FakeSession(
        {REVERSE_GEOCODING_URL: {"address": {"city": "广州市", "state": "广东省"}}}
    )

    city = WeatherService(session=session).city_from_coordinates(23.13, 113.26)

    assert city == "广州"
    assert session.calls[0][0] == REVERSE_GEOCODING_URL


def test_invalid_coordinates_are_rejected() -> None:
    with pytest.raises(WeatherError, match="坐标无效"):
        WeatherService().city_from_coordinates(120, 113.26)


def test_network_timeout_is_mapped_to_weather_error() -> None:
    class TimeoutSession:
        def get(self, *args, **kwargs):
            raise requests.Timeout("timeout")

    with pytest.raises(WeatherError, match="暂时不可用"):
        WeatherService(session=TimeoutSession()).get_today("北京")


def test_incomplete_forecast_uses_safe_error() -> None:
    payloads = _sunny_payloads()
    payloads[FORECAST_URL] = {"current": {}, "daily": {}}

    with pytest.raises(WeatherError, match="字段不完整"):
        WeatherService(session=FakeSession(payloads)).get_today("北京")


@pytest.mark.parametrize(
    ("code", "label"),
    [(0, "晴"), (3, "阴"), (45, "雾"), (61, "雨"), (71, "雪"), (95, "雷")],
)
def test_compact_weather_label(code: int, label: str) -> None:
    assert compact_weather_label(code) == label
