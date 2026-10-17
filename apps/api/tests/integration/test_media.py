"""Attaching video to an athlete.

Two things are worth testing here and neither is the upload itself: who may
reach a clip, and whether taking one down actually removes the file. Footage of
a minor left hosted after a delete is the failure that matters.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bsa.api.app import create_app
from bsa.core.config import Settings, get_settings
from bsa.db.models import Organization, Player, SessionVideo
from bsa.db.session import get_db
from bsa.domain.enums import Role
from bsa.integrations.media.base import StoredMedia
from tests.conftest import make_player, make_user

pytestmark = pytest.mark.integration

COACH = {"Authorization": "Bearer dev|coach"}
PLAYER = {"Authorization": "Bearer dev|player"}
OTHER = {"Authorization": "Bearer dev|other"}

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


@dataclass
class FakeMediaStore:
    """Stands in for Cloudinary. Records what it was asked to do."""

    name: str = "fake"
    uploaded: dict[str, bytes] = field(default_factory=dict)
    deleted: list[str] = field(default_factory=list)
    signed: list[str] = field(default_factory=list)

    def upload(self, data: bytes, *, filename: str, folder: str) -> StoredMedia:
        asset_id = f"{folder}/{uuid.uuid4().hex}"
        self.uploaded[asset_id] = data
        return StoredMedia(
            asset_id=asset_id,
            url=f"https://cdn.test/{asset_id}",
            thumbnail_url=f"https://cdn.test/{asset_id}.jpg",
            byte_size=len(data),
        )

    def playback_url(self, asset_id: str, *, fallback: str) -> str:
        # A fresh signature each time, which is the behaviour being relied on.
        self.signed.append(asset_id)
        return f"https://cdn.test/{asset_id}?sig={len(self.signed)}"

    def delete(self, asset_id: str) -> None:
        self.deleted.append(asset_id)
        self.uploaded.pop(asset_id, None)


@pytest.fixture
def store() -> FakeMediaStore:
    return FakeMediaStore()


@pytest.fixture
def client(db: Session, store: FakeMediaStore, monkeypatch):  # type: ignore[no-untyped-def]
    settings = Settings(env="development", auth_provider="dev", media_provider="local")
    monkeypatch.setattr("bsa.api.v1.media.get_media_store", lambda _settings: store)
    monkeypatch.setattr("bsa.api.v1.hitting.get_media_store", lambda _settings: store)

    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture
def athlete(db: Session, organization: Organization) -> Player:
    player = make_player(
        db, organization, first_name="Jordan", last_name="Avery", external_id="TM-MEDIA-1"
    )
    other = make_player(
        db, organization, first_name="Riley", last_name="Chen", external_id="TM-MEDIA-2"
    )
    make_user(db, organization, subject="dev|coach", role=Role.COACH)
    make_user(db, organization, subject="dev|player", role=Role.PLAYER, player=player)
    make_user(db, organization, subject="dev|other", role=Role.PLAYER, player=other)
    db.flush()
    return player


def upload(client: TestClient, player: Player, headers=COACH, name: str = "swing.mp4"):  # type: ignore[no-untyped-def]
    return client.post(
        f"/api/v1/players/{player.id}/videos",
        headers=headers,
        files={"file": (name, MP4, "video/mp4")},
        data={"title": "Swing on pitch 41"},
    )


class TestUploading:
    def test_a_coach_can_attach_a_clip(
        self, client: TestClient, athlete: Player, store: FakeMediaStore
    ) -> None:
        response = upload(client, athlete)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["title"] == "Swing on pitch 41"
        assert len(store.uploaded) == 1

    def test_the_bytes_go_to_the_provider_not_the_database(
        self, client: TestClient, db: Session, athlete: Player, store: FakeMediaStore
    ) -> None:
        upload(client, athlete)

        video = db.query(SessionVideo).one()
        assert video.external_asset_id in store.uploaded
        assert video.provider == "fake"
        # What is stored is a reference, never the file.
        assert MP4 not in video.url.encode()

    def test_a_clip_needs_no_session(
        self, client: TestClient, db: Session, athlete: Player
    ) -> None:
        """A coach usually has the clip before deciding where it belongs."""
        assert upload(client, athlete).status_code == 201
        assert db.query(SessionVideo).one().session_id is None

    def test_a_player_cannot_upload(self, client: TestClient, athlete: Player) -> None:
        assert upload(client, athlete, headers=PLAYER).status_code == 403

    @pytest.mark.parametrize("name", ["notes.pdf", "swing.exe", "clip.txt"])
    def test_a_file_that_is_not_a_video_is_refused(
        self, client: TestClient, athlete: Player, name: str
    ) -> None:
        response = client.post(
            f"/api/v1/players/{athlete.id}/videos",
            headers=COACH,
            files={"file": (name, b"not a video", "application/pdf")},
        )
        assert response.status_code == 422

    def test_an_oversized_file_is_refused_and_says_how_big_it_was(
        self, db: Session, athlete: Player, store: FakeMediaStore, monkeypatch
    ) -> None:
        """An upload runs through the API process, so the cap is real. Saying
        only "too large" leaves a coach guessing how much to trim."""
        settings = Settings(
            env="development",
            auth_provider="dev",
            media_provider="local",
            max_video_megabytes=1,
        )
        monkeypatch.setattr("bsa.api.v1.media.get_media_store", lambda _s: store)
        app = create_app(settings)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_settings] = lambda: settings
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            f"/api/v1/players/{athlete.id}/videos",
            headers=COACH,
            files={"file": ("big.mp4", b"\x00" * 2_000_000, "video/mp4")},
            data={"title": "big"},
        )

        assert response.status_code == 422
        assert "2 MB" in response.json()["error"]["message"]
        assert "1 MB limit" in response.json()["error"]["message"]
        assert store.uploaded == {}


class TestWhoCanWatch:
    def test_an_athlete_sees_their_own_clips_without_sending_an_id(
        self, client: TestClient, athlete: Player
    ) -> None:
        upload(client, athlete)

        response = client.get("/api/v1/me/videos", headers=PLAYER)

        assert response.status_code == 200
        assert [v["title"] for v in response.json()] == ["Swing on pitch 41"]

    def test_an_athlete_cannot_reach_another_athletes_clips(
        self, client: TestClient, athlete: Player
    ) -> None:
        upload(client, athlete)

        response = client.get(f"/api/v1/players/{athlete.id}/videos", headers=OTHER)

        # 404, not 403: the difference would confirm the athlete is enrolled.
        assert response.status_code == 404

    def test_a_playback_url_is_minted_per_request(
        self, client: TestClient, athlete: Player, store: FakeMediaStore
    ) -> None:
        """A URL saved in a row outlives the permission that produced it, and
        an authenticated asset is deliberately unreachable without a fresh
        signature."""
        upload(client, athlete)

        first = client.get("/api/v1/me/videos", headers=PLAYER).json()[0]["playback_url"]
        second = client.get("/api/v1/me/videos", headers=PLAYER).json()[0]["playback_url"]

        assert first != second
        assert len(store.signed) >= 2


class TestRemoval:
    def test_deleting_takes_the_file_down_too(
        self, client: TestClient, db: Session, athlete: Player, store: FakeMediaStore
    ) -> None:
        """A row deleted on its own leaves footage of a minor hosted and
        reachable by anyone holding the link."""
        video_id = upload(client, athlete).json()["id"]
        asset_id = db.query(SessionVideo).one().external_asset_id

        response = client.delete(f"/api/v1/videos/{video_id}", headers=COACH)

        assert response.status_code == 204
        assert store.deleted == [asset_id]
        assert store.uploaded == {}
        assert db.query(SessionVideo).count() == 0

    def test_a_player_cannot_delete(self, client: TestClient, athlete: Player) -> None:
        video_id = upload(client, athlete).json()["id"]
        assert client.delete(f"/api/v1/videos/{video_id}", headers=PLAYER).status_code == 403
