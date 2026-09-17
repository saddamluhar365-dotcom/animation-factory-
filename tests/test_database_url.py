from sqlalchemy.engine import make_url

from core.db.bootstrap import database_url


def test_database_url_preserves_reserved_characters_in_password(monkeypatch):
    monkeypatch.setenv("YT_AUTO_DB_HOST", "127.0.0.1")
    monkeypatch.setenv("YT_AUTO_DB_PORT", "5432")
    monkeypatch.setenv("YT_AUTO_DB_NAME", "ai_shorts_factory")
    monkeypatch.setenv("YT_AUTO_DB_USER", "ai_shorts_factory")
    monkeypatch.setenv("YT_AUTO_DB_PASSWORD", "Armaan@5537:p%ss#word")

    url = make_url(database_url())

    assert url.username == "ai_shorts_factory"
    assert url.password == "Armaan@5537:p%ss#word"
    assert url.host == "127.0.0.1"
    assert url.port == 5432
    assert url.database == "ai_shorts_factory"
