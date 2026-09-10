"""Open-Meteo 城市解析、今日天气与晾晒判断。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REVERSE_GEOCODING_URL = "https://nominatim.openstreetmap.org/reverse"


class WeatherError(RuntimeError):
    """天气服务无法返回可用数据。"""


@dataclass(frozen=True, slots=True)
class WeatherSummary:
    city: str
    resolved_location: str
    forecast_date: str
    condition: str
    weather_code: int
    current_temperature: float
    minimum_temperature: float
    maximum_temperature: float
    precipitation_probability: int
    relative_humidity: int
    wind_speed: float
    is_sunny: bool
    is_suitable_for_drying: bool
    drying_label: str
    source: str
    fetched_at: str


WEATHER_LABELS = {
    0: "晴",
    1: "大部晴朗",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "较强阵雨",
    82: "强阵雨",
    95: "雷暴",
    96: "雷暴伴冰雹",
    99: "强雷暴伴冰雹",
}


def compact_weather_label(weather_code: int) -> str:
    """把详细天气代码压缩成首页使用的单字分类。"""

    if weather_code in (0, 1):
        return "晴"
    if weather_code in (2, 3):
        return "阴"
    if weather_code in (45, 48):
        return "雾"
    if 71 <= weather_code <= 77 or weather_code in (85, 86):
        return "雪"
    if weather_code >= 95:
        return "雷"
    return "雨"



class WeatherService:
    def __init__(self, *, session: Any | None = None, timeout: float = 8.0) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise WeatherError("天气服务暂时不可用，请稍后重试。") from error
        if not isinstance(payload, dict):
            raise WeatherError("天气服务返回了无法识别的数据。")
        return payload

    def city_from_coordinates(self, latitude: float, longitude: float) -> str:
        """把用户主动授权的位置转换为城市名，仅在定位按钮触发后调用。"""

        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise WeatherError("定位坐标无效，请手动选择城市。")
        try:
            response = self.session.get(
                REVERSE_GEOCODING_URL,
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "format": "jsonv2",
                    "accept-language": "zh-CN,zh",
                    "zoom": 10,
                },
                headers={"User-Agent": "SmartLaundryAgent/0.1"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise WeatherError("暂时无法识别当前位置，请手动选择城市。") from error
        if not isinstance(payload, dict):
            raise WeatherError("暂时无法识别当前位置，请手动选择城市。")
        address = payload.get("address") or {}
        city = next(
            (
                address.get(key)
                for key in ("city", "municipality", "town", "county", "village", "state")
                if address.get(key)
            ),
            None,
        )
        if not city:
            raise WeatherError("当前位置没有匹配到城市，请手动选择。")
        return str(city).removesuffix("市").strip()

    def get_today(self, city: str) -> WeatherSummary:
        cleaned_city = city.strip()
        if not cleaned_city:
            raise WeatherError("请填写城市名称。")

        geocoding = self._get_json(
            GEOCODING_URL,
            {"name": cleaned_city, "count": 1, "language": "zh", "format": "json"},
        )
        results = geocoding.get("results") or []
        if not results:
            raise WeatherError("没有找到该城市，请尝试更具体的名称。")
        location = results[0]

        forecast = self._get_json(
            FORECAST_URL,
            {
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "current": (
                    "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
                ),
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max"
                ),
                "timezone": "auto",
                "forecast_days": 1,
            },
        )

        try:
            current = forecast["current"]
            daily = forecast["daily"]
            weather_code = int(daily["weather_code"][0])
            humidity = int(current["relative_humidity_2m"])
            rain_probability = int(daily["precipitation_probability_max"][0] or 0)
            is_sunny = weather_code in (0, 1)
            suitable = weather_code <= 2 and rain_probability < 40 and humidity < 85
            if suitable:
                drying_label = "适合户外晾晒"
            elif rain_probability >= 40 or weather_code >= 51:
                drying_label = "不建议户外晾晒"
            else:
                drying_label = "可谨慎安排晾晒"

            admin = location.get("admin1")
            resolved = " · ".join(
                part for part in (location.get("name"), admin, location.get("country")) if part
            )
            return WeatherSummary(
                city=cleaned_city,
                resolved_location=resolved,
                forecast_date=str(daily["time"][0]),
                condition=WEATHER_LABELS.get(weather_code, f"天气代码 {weather_code}"),
                weather_code=weather_code,
                current_temperature=float(current["temperature_2m"]),
                minimum_temperature=float(daily["temperature_2m_min"][0]),
                maximum_temperature=float(daily["temperature_2m_max"][0]),
                precipitation_probability=rain_probability,
                relative_humidity=humidity,
                wind_speed=float(current["wind_speed_10m"]),
                is_sunny=is_sunny,
                is_suitable_for_drying=suitable,
                drying_label=drying_label,
                source="Open-Meteo",
                fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise WeatherError("天气数据字段不完整，已切换为规则模式。") from error
