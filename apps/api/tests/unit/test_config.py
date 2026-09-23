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


def test_database_target_never_leaks_credentials() -> None:
    """/health reports which database answered, and must not expose the password.

    This exists because two stacks on the same port -- a container and a local
    process, each with its own database -- is indistinguishable from a stale
    dashboard until you can see which one replied.
    """
    from bsa.core.config import Settings

    settings = Settings(
        database_url="postgresql+psycopg://bsa:sup3rs3cret@db:5432/bsa",
    )

    target = settings.database_target

    assert target == "db:5432/bsa"
    assert "sup3rs3cret" not in target
    assert "bsa:" not in target


def test_database_target_handles_an_unparseable_url() -> None:
    from bsa.core.config import Settings

    # A string with no host must report nothing rather than echoing itself
    # back -- a malformed URL can still contain a password.
    for bad in ("not a url", "postgresql://", "", "just-a-path/db"):
        target = Settings(database_url=bad).database_target
        assert target == "unknown", f"{bad!r} -> {target!r}"

    # And credentials are stripped wherever a host does parse.
    assert Settings(database_url="postgresql://u:pw@h:1/d").database_target == "h:1/d"


def test_production_refuses_development_passcodes() -> None:
    """A deployment must never inherit the passcodes from the README."""
    import pytest

    from bsa.core.config import Settings

    for coach, player in (
        ("coach", "player"),
        ("aVeryLongOne", "player"),
        ("short", "alsoShort"),
    ):
        with pytest.raises(ValueError, match="at least 8 characters"):
            Settings(
                env="production",
                auth_provider="passcode",
                coach_passcode=coach,
                player_passcode=player,
                object_store_backend="gcs",
                gcs_bucket="bucket",
            )


def test_production_accepts_real_passcodes() -> None:
    from bsa.core.config import Settings

    settings = Settings(
        env="production",
        auth_provider="passcode",
        coach_passcode="a-long-enough-coach-passcode",
        player_passcode="a-long-enough-player-passcode",
        object_store_backend="gcs",
        gcs_bucket="bucket",
    )

    assert settings.auth_provider == "passcode"
