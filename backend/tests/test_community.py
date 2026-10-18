"""Phase 3 persistence, deterministic discovery, privacy and continuity tests."""
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.seed import DEMO_USER, PROFILES
from app.ai.schemas import CanonAdditions, StoryBible, merge_bible
from app.ai.sdxl import panel_prompt
from tests.test_api import client, create_story, make_draft
from tests.test_ai_workflow import FixtureProvider, source_draft, generate


@pytest.mark.parametrize("kind", ["like", "bookmark", "follow"])
def test_duplicate_actions_and_removals_are_idempotent(client, kind):
    sid = create_story(client)
    def activate(_):
        return client.post(f"/api/stories/{sid}/interactions", json={"kind": kind, "active": True})
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(activate, range(8)))
    assert all(r.status_code == 200 for r in results)
    value = client.get(f"/api/stories/{sid}/engagement").json()
    assert value[f"{kind}_count"] == 1 and value[kind] is True
    for _ in range(2):
        removed = client.post(f"/api/stories/{sid}/interactions", json={"kind": kind, "active": False}).json()
        assert removed[f"{kind}_count"] == 0 and removed[kind] is False


def test_community_library_and_reading_survive_restart_and_are_user_scoped(client, tmp_path):
    sid = create_story(client)
    chapters = client.get(f"/api/stories/{sid}/chapters").json()
    for kind in ("like", "bookmark", "follow"):
        assert client.post(f"/api/stories/{sid}/interactions", json={"kind": kind, "active": True}).status_code == 200
    value = {"chapter_id": chapters[0]["id"], "completed": True, "layout": "comic"}
    first = client.post(f"/api/me/reading/{sid}", json=value).json()
    second = client.post(f"/api/me/reading/{sid}", json=value).json()
    assert first == second and first["completed_position"] == 1
    with TestClient(create_app(Settings(data_dir=tmp_path, _env_file=None))) as restarted:
        assert restarted.get(f"/api/stories/{sid}/engagement").json()["like_count"] == 1
        assert restarted.get(f"/api/me/reading/{sid}").json()["chapter_id"] == chapters[0]["id"]
        library = restarted.get("/api/me/stories").json()
        assert sid in [s["id"] for s in library["bookmarked"]]
        assert sid in [s["id"] for s in library["followed"]]
        assert library["reading"][0]["reading_progress"]["layout"] == "comic"
        repo = restarted.app.state.repo
        other = PROFILES[1]["id"]
        assert asyncio.run(repo.reading_progress(None, other, sid)) is None
        other_library = asyncio.run(repo.user_stories(None, other))
        assert not other_library["bookmarked"] and not other_library["followed"] and not other_library["reading"]
        other_state = asyncio.run(repo.engagement(None, other, sid))
        assert other_state["like_count"] == 1 and not other_state["like"]
        asyncio.run(repo.set_interaction(None, other, sid, "like", False))
        assert restarted.get(f"/api/stories/{sid}/engagement").json()["like_count"] == 1


def test_progress_rejects_foreign_chapters_and_never_loses_completed_position(client):
    sid = "aaaaaaaa-aaaa-4aaa-8aaa-000000000001"
    chapters = client.get(f"/api/stories/{sid}/chapters").json()
    assert client.get(f"/api/me/reading/{sid}").json() is None
    assert client.post(f"/api/me/reading/{sid}", json={"chapter_id": chapters[1]["id"], "completed": True}).json()["completed_position"] == 2
    back = client.post(f"/api/me/reading/{sid}", json={"chapter_id": chapters[0]["id"], "completed": False}).json()
    assert back["position"] == 1 and back["completed_position"] == 2
    foreign = create_story(client)
    assert client.post(f"/api/me/reading/{foreign}", json={"chapter_id": chapters[0]["id"]}).status_code == 422
    assert client.post(f"/api/me/reading/{sid}", json={"chapter_id": str(uuid4())}).status_code == 404
    assert client.post(f"/api/me/reading/{sid}", json={"chapter_id": chapters[0]["id"], "user_id": PROFILES[1]["id"]}).status_code == 422
    assert client.get(f"/api/me/reading/{uuid4()}").status_code == 404


def test_discovery_paginates_filters_and_uses_engagement_then_persisted_updates(client):
    a, b = create_story(client, "PAGE A"), create_story(client, "PAGE B")
    for sid in (a,b):
        client.post(f"/api/stories/{sid}/interactions", json={"kind": "like", "active": True})
    client.post(f"/api/stories/{a}/interactions", json={"kind": "follow", "active": True})
    query = {"search": "PAGE", "page_size": 1, "sort": "trending"}
    first = client.get("/api/discover", params=query).json()
    second = client.get("/api/discover", params={**query, "page": 2}).json()
    assert first["items"][0]["id"] == a and second["items"][0]["id"] == b
    assert first["total"] == 2 and first["has_next"] and not second["has_next"]
    assert client.get("/api/discover", params=query).json() == first
    # A new publication makes an older story most recently updated.
    draft = make_draft(client, a)
    assert client.post(f"/api/drafts/{draft}/publish", json={"expected_version": 1, "approved": True}).status_code == 200
    recent = client.get("/api/discover", params={**query, "sort": "recent"}).json()
    assert recent["items"][0]["id"] == a
    assert not client.get("/api/discover", params={"search": "PAGE", "genre": "Mystery"}).json()["items"]
    assert client.get("/api/discover", params={"search": "%"}).json()["total"] == 0
    assert client.get("/api/discover", params={**query, "page": 10}).json()["items"] == []
    assert client.get("/api/discover?page=0").status_code == 422
    assert client.get("/api/discover?page_size=1000").status_code == 422


def test_discovery_stable_id_tie_break_and_counts(client):
    sid = create_story(client, "TIE ONE")
    other = create_story(client, "TIE TWO")
    with client.app.state.repo.db() as db:
        for story_id in (sid,other):
            value = client.app.state.repo.get(db, "stories", story_id)
            client.app.state.repo.put(db, "stories", {**value, "updated_at": "2026-01-01T00:00:00+00:00"})
    rows = client.get("/api/discover", params={"search": "TIE"}).json()["items"]
    assert [s["id"] for s in rows] == sorted([sid,other])
    assert all(s["like_count"] == s["follow_count"] == s["bookmark_count"] == 0 for s in rows)


def test_auth_and_caller_jwt_for_community_and_progress_without_hosted_supabase(tmp_path):
    settings = Settings(app_mode="supabase", supabase_url="http://supabase.invalid", supabase_anon_key="synthetic-anon", _env_file=None)
    app = create_app(settings)
    seen = []
    sid = str(uuid4())
    def handler(req):
        seen.append(req)
        assert req.headers["authorization"] == "Bearer synthetic-user"
        if req.url.path == "/auth/v1/user": return httpx.Response(200, json={"id": DEMO_USER})
        assert req.url.path == "/rest/v1/rpc/set_story_interaction"
        assert b"user_id" not in req.content
        return httpx.Response(200, json={"story_id": sid, "like": True, "like_count": 1})
    app.state.repo.client = httpx.AsyncClient(base_url=settings.supabase_url, transport=httpx.MockTransport(handler))
    with TestClient(app) as c:
        assert c.post(f"/api/stories/{sid}/interactions", json={"kind": "like", "active": True}).status_code == 401
        assert c.get(f"/api/me/reading/{sid}").status_code == 401
        assert c.post(f"/api/me/reading/{sid}", json={"chapter_id": str(uuid4())}).status_code == 401
        assert not seen
        assert c.post(f"/api/stories/{sid}/interactions", headers={"Authorization": "Bearer synthetic-user"}, json={"kind": "like", "active": True}).status_code == 200
        assert len(seen) == 2


def test_invalid_community_actions_and_missing_story(client):
    sid = create_story(client)
    assert client.post(f"/api/stories/{sid}/interactions", json={"kind": "share", "active": True}).status_code == 422
    assert client.post(f"/api/stories/{sid}/interactions", json={"kind": "like", "active": True, "user_id": PROFILES[1]["id"]}).status_code == 422
    assert client.post(f"/api/stories/{uuid4()}/interactions", json={"kind": "like", "active": True}).status_code == 404


def test_visual_traits_relationships_and_events_are_append_only():
    original = {"characters": [{"name": "Elara", "description": "A village herbalist.", "visual_description": "A grey coat and a brass key.",
        "personality_traits": ["Patient"], "relationships": ["Knows the fox."]}], "important_events": ["The river stopped."]}
    baseline = copy.deepcopy(original)
    merged = merge_bible(original, CanonAdditions(characters=[{"name": "Elara", "description": "A village herbalist.",
        "visual_description": "A grey coat and a brass key.", "personality_traits": ["Patient", "Brave"], "relationships": ["Trusts the fox."]}], important_events=["The bell rang."]))
    assert merged["characters"][0]["personality_traits"] == ["Patient", "Brave"]
    assert merged["important_events"] == ["The river stopped.", "The bell rang."]
    assert len(merged["characters"][0]["relationships"]) == 2 and original == baseline
    with pytest.raises(ValueError, match="visual description"):
        merge_bible(original, CanonAdditions(characters=[{"name": "Elara", "description": "A village herbalist.", "visual_description": "A bright red spacesuit."}]))
    # Historical entries without new fields stay valid and gain safe empty defaults.
    assert StoryBible.model_validate({"characters": [{"name": "Old friend", "description": "A traveler."}]}).characters[0].personality_traits == []
    prompt = panel_prompt({"description": "A traveler on a bridge.", "characters": ["Elara"], "location": "River", "camera": "Wide"}, merged)
    assert "A grey coat and a brass key." in prompt


def test_published_bible_and_original_sample_chapters_are_preserved(client):
    sid = "aaaaaaaa-aaaa-4aaa-8aaa-000000000001"
    before = client.get(f"/api/stories/{sid}/chapters").json()
    bible = client.get(f"/api/stories/{sid}/bible").json()
    assert len(before) == 3 and bible["version"] == 3
    assert bible["data"]["characters"][1]["visual_description"].startswith("An old fox")
    assert bible["data"]["characters"][0]["personality_traits"]
    make_draft(client, sid, version=3)
    assert client.get(f"/api/stories/{sid}/chapters").json() == before
    assert client.get(f"/api/stories/{sid}/bible").json() == bible


def test_continuity_failure_preserves_draft_and_canon_before_publication(tmp_path):
    class ConflictingProvider(FixtureProvider):
        async def structured(self, task, data, schema):
            result = await super().structured(task, data, schema)
            result.value.memory.additions.characters[0].visual_description = "A red spacesuit."
            return result
    settings = Settings(data_dir=tmp_path, ai_mode="gemini", gemini_api_key="fixture-only", gemini_free_tier_confirmed=True, _env_file=None)
    with TestClient(create_app(settings, ConflictingProvider())) as c:
        sid, draft = source_draft(c)
        with c.app.state.repo.db() as db:
            row = c.app.state.repo.get(db, "story_bibles", sid)
            row["data"]["characters"] = [{"name": "The stranger", "description": "A traveler in a grey coat carrying a worn brass compass.",
                "visual_description": "A grey coat.", "personality_traits": [], "relationships": []}]
            c.app.state.repo.put(db, "story_bibles", row)
        # Match the fixture's canonical description so visual consistency is tested.
        from tests.ai_fixtures import chapter_payload
        with c.app.state.repo.db() as db:
            row = c.app.state.repo.get(db, "story_bibles", sid)
            row["data"]["characters"][0]["name"] = chapter_payload()["memory"]["additions"]["characters"][0]["name"]
            row["data"]["characters"][0]["description"] = chapter_payload()["memory"]["additions"]["characters"][0]["description"]
            c.app.state.repo.put(db, "story_bibles", row)
        canon = c.get(f"/api/stories/{sid}/bible").json()
        failed = generate(c, draft)
        assert failed.status_code == 502 and failed.json()["code"] == "continuity_validation"
        assert c.get(f"/api/drafts/{draft}").status_code == 200
        assert c.get(f"/api/stories/{sid}/bible").json() == canon
