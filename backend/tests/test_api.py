from concurrent.futures import ThreadPoolExecutor
import io
import wave
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.seed import DEMO_USER, PROFILES


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(app_mode="demo", data_dir=tmp_path, _env_file=None))) as app:
        yield app


def create_story(client, title="Test story"):
    response = client.post("/api/stories", json={"title": title, "genre": "Fantasy", "narrative": "The door had been here all along."})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def make_draft(client, story_id, text="Beyond the door, a second sun was rising.", version=1):
    response = client.post(f"/api/stories/{story_id}/contributions", json={"text": text, "direction": "Add a twist", "expected_version": version})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_demo_is_explicit_and_filters_work(client):
    health = client.get("/api/health").json()
    assert health["mode"] == "demo" and not health["ai_enabled"]
    stories = client.get("/api/stories").json()
    assert len(stories) == 6 and all(s["is_demo"] for s in stories)
    assert stories[0]["contributor_count"] == 3
    filtered = client.get("/api/stories", params={"search": "forest", "genre": "Fantasy"}).json()
    assert len(filtered) == 1
    assert client.get("/api/stories?sort=invalid").status_code == 422
    assert client.get("/api/stories/not-a-uuid").status_code == 422


def test_create_publish_and_persistence(client, tmp_path):
    sid = create_story(client)
    did = make_draft(client, sid)
    draft = client.get(f"/api/drafts/{did}").json()
    assert draft["narrative"] == "Beyond the door, a second sun was rising."
    assert draft["source"] == "demo_preview"
    assert len(client.get(f"/api/stories/{sid}/chapters").json()) == 1
    assert client.patch(f"/api/drafts/{did}", json={"title": "Two suns", "narrative": "My reviewed chapter."}).status_code == 200
    assert client.post(f"/api/drafts/{did}/publish", json={"expected_version": 1, "approved": False}).status_code == 422
    response = client.post(f"/api/drafts/{did}/publish", json={"expected_version": 1, "approved": True})
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    chapters = client.get(f"/api/stories/{sid}/chapters").json()
    assert chapters[-1]["title"] == "Two suns"
    assert chapters[-1]["narrative"] == "My reviewed chapter."
    assert chapters[-1]["author"]["id"] == DEMO_USER
    assert client.post(f"/api/drafts/{did}/publish", json={"expected_version": 2, "approved": True}).status_code == 409
    assert client.patch(f"/api/drafts/{did}", json={"title": "Changed", "narrative": "No"}).status_code == 409
    with TestClient(create_app(Settings(app_mode="demo", data_dir=tmp_path, _env_file=None))) as restarted:
        assert restarted.get(f"/api/stories/{sid}").json()["version"] == 2


def test_concurrent_publish_has_exactly_one_winner(client):
    sid = create_story(client)
    drafts = [make_draft(client, sid, f"Version from contributor {i}.") for i in range(2)]
    def publish(did):
        return client.post(f"/api/drafts/{did}/publish", json={"expected_version": 1, "approved": True}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(publish, drafts))
    assert sorted(results) == [200, 409]
    story = client.get(f"/api/stories/{sid}").json()
    assert story["version"] == 2 and len(story["chapters"]) == 2
    assert len(client.get("/api/drafts").json()) == 1
    assert client.post(f"/api/stories/{sid}/contributions", json={"text": "Stale", "expected_version": 1}).status_code == 409


def test_draft_owner_checks_and_preview_reset(client):
    sid = create_story(client)
    did = make_draft(client, sid, "Original, unchanged words.")
    repo = client.app.state.repo
    with repo.db() as db:
        draft = repo.get(db, "drafts", did)
        repo.put(db, "drafts", {**draft, "owner_id": PROFILES[1]["id"]})
    assert client.get(f"/api/drafts/{did}").status_code == 404
    assert client.patch(f"/api/drafts/{did}", json={"title": "Steal", "narrative": "No"}).status_code == 404
    assert client.post(f"/api/drafts/{did}/publish", json={"expected_version": 1, "approved": True}).status_code == 404
    with repo.db() as db:
        repo.put(db, "drafts", draft)
    client.patch(f"/api/drafts/{did}", json={"title": "Changed", "narrative": "Edited"})
    reset = client.post(f"/api/drafts/{did}/regenerate").json()
    assert reset["narrative"] == "Original, unchanged words."


def test_upload_validation_and_publication(client):
    assert client.post("/api/uploads", files={"file": ("bad.svg", b"<svg/>", "image/svg+xml")}).status_code == 415
    assert client.post("/api/uploads", files={"file": ("bad.png", b"<html/>", "image/png")}).status_code == 415
    png = b"\x89PNG\r\n\x1a\n" + b"sample"
    upload = client.post("/api/uploads", files={"file": ("../../cover.png", png, "image/png")})
    assert upload.status_code == 201, upload.text
    item = upload.json()
    assert item["filename"] == "cover.png" and not item["is_public"]
    assert client.get(item["url"]).content == png
    sid = create_story(client)
    did = client.post(f"/api/stories/{sid}/contributions", json={"text": "An illustrated chapter", "expected_version": 1, "upload_ids": [item["id"]]}).json()["id"]
    assert client.post(f"/api/drafts/{did}/publish", json={"approved": True, "expected_version": 1}).status_code == 200
    chapter = client.get(f"/api/stories/{sid}/chapters").json()[-1]
    assert chapter["panels"][0]["id"] == item["id"]
    with client.app.state.repo.db() as db:
        assert client.app.state.repo.get(db, "uploads", item["id"])["is_public"]


def test_validation_and_profile(client):
    assert client.post("/api/stories", json={"title": "   ", "genre": "Fantasy", "narrative": "x"}).status_code == 422
    assert client.post("/api/stories", json={"title": "x", "genre": "invalid", "narrative": "x"}).status_code == 422
    sid = create_story(client)
    assert client.post(f"/api/stories/{sid}/contributions", json={"text": "", "expected_version": 1}).status_code == 422
    assert client.patch("/api/me", json={"display_name": "A Writer", "bio": "Hello"}).status_code == 200
    assert client.get("/api/me").json()["display_name"] == "A Writer"
    assert len(client.get("/api/me/stories").json()["created"]) == 3


def test_media_limits_and_foreign_uploads(client):
    content = io.BytesIO()
    with wave.open(content, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 80)
    uploaded = client.post("/api/uploads", files={"file": ("voice.wav", content.getvalue(), "audio/wav")})
    assert uploaded.status_code == 201
    assert client.get(uploaded.json()["url"]).content == content.getvalue()
    sid = create_story(client)
    item_id = uploaded.json()["id"]
    duplicate = client.post(f"/api/stories/{sid}/contributions", json={"text": "Duplicate", "expected_version": 1, "upload_ids": [item_id, item_id]})
    assert duplicate.status_code == 422
    with client.app.state.repo.db() as db:
        item = client.app.state.repo.get(db, "uploads", item_id)
        client.app.state.repo.put(db, "uploads", {**item, "owner_id": PROFILES[1]["id"]})
    denied = client.post(f"/api/stories/{sid}/contributions", json={"text": "Foreign", "expected_version": 1, "upload_ids": [item_id]})
    assert denied.status_code == 403
    assert client.get(uploaded.json()["url"]).status_code == 404
    client.app.state.settings.max_upload_bytes = 10
    assert client.post("/api/uploads", files={"file": ("voice.wav", content.getvalue(), "audio/wav")}).status_code == 413


def test_supabase_mode_fails_closed_without_credentials(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(Settings(app_mode="supabase", supabase_url="", supabase_anon_key="", data_dir=tmp_path, _env_file=None))


def test_supabase_verifies_identity_and_forwards_caller_jwt(tmp_path):
    app = create_app(Settings(app_mode="supabase", supabase_url="https://example.supabase.co", supabase_anon_key="public-test-key", data_dir=tmp_path, _env_file=None))
    seen = []
    def handle(req):
        seen.append(req)
        if req.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": DEMO_USER}) if req.headers.get("Authorization") == "Bearer valid-user-token" else httpx.Response(401, json={})
        if req.url.path == "/rest/v1/profiles":
            return httpx.Response(200, json=[PROFILES[0]])
        return httpx.Response(400, json={"code": "40001"})
    app.state.repo.client = httpx.AsyncClient(base_url="https://example.supabase.co", transport=httpx.MockTransport(handle))
    with TestClient(app) as client:
        assert client.get("/api/me").status_code == 401
        assert client.get("/api/me", headers={"Authorization": "Bearer fake"}).status_code == 401
        response = client.get("/api/me", headers={"Authorization": "Bearer valid-user-token"})
        assert response.status_code == 200
        assert seen[-1].headers["Authorization"] == "Bearer valid-user-token"
        assert seen[-1].headers["apikey"] == "public-test-key"
        did = str(uuid4())
        conflict = client.post(f"/api/drafts/{did}/publish", headers={"Authorization": "Bearer valid-user-token"}, json={"approved": True, "expected_version": 1})
        assert conflict.status_code == 409
