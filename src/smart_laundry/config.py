"""集中读取项目配置，避免在页面和业务代码中散落环境变量。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    """应用启动时需要的最小配置。"""

    default_city: str
    database_path: Path
    openai_api_key: str | None
    openai_model: str | None
    openai_base_url: str | None

    @property
    def has_openai_key(self) -> bool:
        """只暴露是否已配置密钥，避免页面显示密钥内容。"""

        return bool(self.openai_api_key)


def _resolve_database_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def get_settings(*, load_env_file: bool = True) -> Settings:
    """从环境变量读取配置；测试可关闭 .env 加载以保持隔离。"""

    if load_env_file:
        load_dotenv(PROJECT_ROOT / ".env")

    return Settings(
        default_city=os.getenv("DEFAULT_CITY", "北京").strip() or "北京",
        database_path=_resolve_database_path(
            os.getenv("DATABASE_PATH", "data/smart_laundry.db")
        ),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL") or None,
        openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
    )
