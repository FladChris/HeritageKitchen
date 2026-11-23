import pytest

from app.core.config import Settings


@pytest.mark.parametrize("value", [None, "", "   "])
def test_database_defaults_to_sqlite(monkeypatch, value):
    monkeypatch.delenv("SQLITE_DATABASE_PATH", raising=False)
    if value is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", value)
    assert Settings().database_url == "sqlite:///./heritagekitchen.db"


def test_database_uses_persistent_sqlite_path(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SQLITE_DATABASE_PATH", "/data/heritagekitchen.db")
    assert Settings().database_url == "sqlite:////data/heritagekitchen.db"


def test_database_preserves_external_postgresql(monkeypatch):
    url = "postgresql+psycopg://user:password@postgres:5432/heritagekitchen"
    monkeypatch.setenv("DATABASE_URL", url)
    assert Settings().database_url == url


def test_app_version_defaults_to_project_version(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)

    assert Settings().app_version == "0.1.0"


def test_app_version_uses_environment(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "1.0.0-alpha.1")

    assert Settings().app_version == "1.0.0-alpha.1"
