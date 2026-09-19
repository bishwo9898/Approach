"""Runtime configuration tests."""

from bsa.core.config import Settings


def test_cors_origins_accepts_comma_separated_environment_value(monkeypatch) -> None:
    monkeypatch.setenv(
        "BSA_CORS_ORIGINS",
        "https://dashboard.example.test, https://players.example.test",
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == [
        "https://dashboard.example.test",
        "https://players.example.test",
    ]
