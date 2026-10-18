"""Opt-in integration test. Use a disposable migrated Supabase project.

This intentionally leaves one [Integration test] story and its published files.
Set STORYVERSE_LIVE_TESTS=1 and the test credentials described in README.md.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


@pytest.mark.skipif(os.getenv("STORYVERSE_LIVE_TESTS") != "1", reason="Live Supabase test requires explicit opt-in and a disposable project")
def test_real_supabase_auth_storage_rls_and_publish(tmp_path):
    from dotenv import load_dotenv
    load_dotenv(os.getenv("STORYVERSE_LIVE_ENV_FILE", ".env"), override=False)
    # This test validates hosted accounts/storage/manual publication only. It
    # must not need the separate worker's service credential or GPU runtime.
    settings = Settings(app_mode="supabase", data_dir=tmp_path, sdxl_execution="local", sdxl_enabled=False)
    settings.validate_mode()
    tokens = []
    for suffix in ("A", "B"):
        result = httpx.post(f"{settings.supabase_url.rstrip('/')}/auth/v1/token", params={"grant_type": "password"},
            headers={"apikey": settings.supabase_anon_key},
            json={"email": os.environ[f"SUPABASE_TEST_EMAIL_{suffix}"], "password": os.environ[f"SUPABASE_TEST_PASSWORD_{suffix}"]})
        assert result.status_code == 200, f"Test account {suffix} could not sign in"
        tokens.append(result.json()["access_token"])
    headers_a, headers_b = [{"Authorization": f"Bearer {token}"} for token in tokens]
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/me").status_code == 401
        assert client.get("/api/me", headers=headers_a).status_code == 200
        assert client.get("/api/me", headers=headers_b).status_code == 200
        png = __import__("base64").b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a4Z8AAAAASUVORK5CYII=")
        uploaded = client.post("/api/uploads", headers=headers_a, files={"file": ("sample.png", png, "image/png")})
        assert uploaded.status_code == 201, uploaded.text
        upload = uploaded.json()
        assert client.get(upload["url"]).status_code == 404
        assert client.get(upload["url"], headers=headers_b).status_code == 404
        assert client.get(upload["url"], headers=headers_a).content == png
        created = client.post("/api/stories", headers=headers_a, json={"title": f"[Integration test] {uuid4()}", "genre": "Mystery", "narrative": "A real persistence test."})
        assert created.status_code == 201, created.text
        sid = created.json()["id"]
        assert client.get(f"/api/stories/{sid}").status_code == 200
        drafts = []
        for headers, attachments in ((headers_a, [upload["id"]]), (headers_b, [])):
            response = client.post(f"/api/stories/{sid}/contributions", headers=headers, json={"text": "My reviewed, manual contribution.", "expected_version": 1, "upload_ids": attachments})
            assert response.status_code == 201, response.text
            drafts.append(response.json()["id"])
        assert client.get(f"/api/drafts/{drafts[0]}", headers=headers_b).status_code == 404
        assert client.get(f"/api/drafts/{drafts[0]}").status_code == 401
        def publish(args):
            did, headers = args
            return client.post(f"/api/drafts/{did}/publish", headers=headers, json={"approved": True, "expected_version": 1}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(publish, zip(drafts, (headers_a, headers_b)))) == [200,409]
        story = client.get(f"/api/stories/{sid}").json()
        assert story["version"] == 2 and len(story["chapters"]) == 2
        # If B won the race, publish A's media through a fresh draft based on version 2.
        if not story["chapters"][-1]["attachments"]:
            did = client.post(f"/api/stories/{sid}/contributions", headers=headers_a, json={"text": "A published media test.", "expected_version": 2, "upload_ids": [upload["id"]]}).json()["id"]
            assert client.post(f"/api/drafts/{did}/publish", headers=headers_a, json={"approved": True, "expected_version": 2}).status_code == 200
        assert client.get(upload["url"]).content == png
        # Phase 3: real community rows, idempotence and private reading/library state.
        for _ in range(2):
            result = client.post(f"/api/stories/{sid}/interactions", headers=headers_a, json={"kind":"like","active":True})
            assert result.status_code == 200 and result.json()["like_count"] == 1
        for kind in ("bookmark","follow"):
            assert client.post(f"/api/stories/{sid}/interactions", headers=headers_a, json={"kind":kind,"active":True}).status_code == 200
        assert client.get(f"/api/stories/{sid}/engagement").json()["like_count"] == 1
        assert client.get(f"/api/stories/{sid}/engagement", headers=headers_b).json()["bookmark"] is False
        chapter_id = client.get(f"/api/stories/{sid}/chapters").json()[0]["id"]
        assert client.post(f"/api/me/reading/{sid}", headers=headers_a, json={"chapter_id":chapter_id,"completed":True,"layout":"comic"}).status_code == 200
        assert client.get(f"/api/me/reading/{sid}", headers=headers_b).json() is None
        library_a = client.get("/api/me/stories", headers=headers_a).json()
        library_b = client.get("/api/me/stories", headers=headers_b).json()
        assert sid in [s["id"] for s in library_a["bookmarked"]]
        assert sid not in [s["id"] for s in library_b["bookmarked"]]
        discovery = client.get("/api/discover", params={"search":story["title"],"page_size":1}).json()
        assert discovery["total"] == 1 and discovery["items"][0]["id"] == sid
