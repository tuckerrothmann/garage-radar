from garage_radar.config import Settings


def test_settings_ignore_unrelated_env_vars(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/test_db")
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("FRONTEND_BROWSER_API_URL", "http://localhost:8000")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql://postgres:postgres@localhost:5432/test_db"
