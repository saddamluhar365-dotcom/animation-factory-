import pytest
from sqlalchemy.engine import make_url

from core.db.bootstrap import database_url


@pytest.mark.parametrize(
    "test_password",
    [
        "normal password",
        "password@",
        "password:",
        "password/",
        "password?",
        "password#",
        "password%",
        "password with spaces",
        "Armaan@5537:p%ss#word",
        "p@ss:w/o?r#d%&=+ 123!$^&*()",
    ],
)
def test_database_url_preserves_reserved_characters_in_password(monkeypatch, test_password):
    monkeypatch.setenv("YT_AUTO_DB_HOST", "127.0.0.1")
    monkeypatch.setenv("YT_AUTO_DB_PORT", "5432")
    monkeypatch.setenv("YT_AUTO_DB_NAME", "ai_shorts_factory")
    monkeypatch.setenv("YT_AUTO_DB_USER", "ai_shorts_factory")
    monkeypatch.setenv("YT_AUTO_DB_PASSWORD", test_password)

    raw_url = database_url()
    parsed = make_url(raw_url)

    assert parsed.username == "ai_shorts_factory"
    assert parsed.password == test_password
    assert parsed.host == "127.0.0.1"
    assert parsed.port == 5432
    assert parsed.database == "ai_shorts_factory"


def test_database_url_prefers_direct_url_env(monkeypatch):
    custom_url = "postgresql+psycopg://custom_user:custom_pass@db.local:5433/custom_db"
    monkeypatch.setenv("YT_AUTO_DB_URL", custom_url)
    assert database_url() == custom_url


def test_database_url_handles_invalid_port_gracefully(monkeypatch):
    monkeypatch.setenv("YT_AUTO_DB_PORT", "invalid_port")
    parsed = make_url(database_url())
    assert parsed.port == 5432
