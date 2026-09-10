"""浏览器设备定位组件；仅在用户尚未保存城市时尝试一次。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_FRONTEND_PATH = Path(__file__).with_name("device_location_frontend")
_device_location = components.declare_component(
    "smart_laundry_device_location", path=str(_FRONTEND_PATH)
)


def get_device_location(*, enabled: bool, key: str) -> dict[str, Any] | None:
    """在手机浏览器中请求一次位置；电脑端直接返回不支持自动定位。"""

    return _device_location(enabled=enabled, key=key, default=None)
