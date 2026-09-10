from pathlib import Path

from smart_laundry.config import PROJECT_ROOT, get_settings


def test_default_settings_work_without_secrets(monkeypatch) -> None:
    for name in (
        "DEFAULT_CITY",
        "DATABASE_PATH",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = get_settings(load_env_file=False)

    assert settings.default_city == "北京"
    assert settings.database_path == PROJECT_ROOT / "data" / "smart_laundry.db"
    assert settings.has_openai_key is False


def test_relative_database_path_is_resolved_from_project_root(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_PATH", "data/test.db")

    settings = get_settings(load_env_file=False)

    assert settings.database_path == Path(PROJECT_ROOT, "data", "test.db")
