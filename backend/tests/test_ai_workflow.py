import asyncio
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.ai.providers import AIProvider, ProviderResult, GenerationError
from app.ai.schemas import GeneratedChapter, MemoryOutput, ComicPrompt
from app.ai.context import StoryContextBuilder
from app.seed import DEMO_USER, PROFILES
from tests.ai_fixtures import chapter_payload


class FixtureProvider(AIProvider):
    is_test_fixture = True
    name = "gemini"
    def __init__(self):
        self.calls = []
        self.error = None
        self.started = threading.Event()
        self.release = None
    async def structured(self, task, data, schema):
        self.calls.append((task, copy.deepcopy(data)))
        self.started.set()
        if self.release:
            while not self.release.is_set():
                await asyncio.sleep(.01)
        if self.error:
            raise self.error
        value = chapter_payload()
        if schema == MemoryOutput:
            value = value["memory"]
            value["summary"]["synopsis"] = "Summary of the final reviewed words."
        elif schema == ComicPrompt:
            value = value["panels"][0]
            value["description"] = "A regenerated close-up description of Elara's brass key and the stranger's compass beside the wooden bridge."
        return ProviderResult(schema.model_validate(value), 1800, 700, "gemini-test-fixture")


@pytest.fixture
def ai_client(tmp_path):
    provider = FixtureProvider()
    settings = Settings(data_dir=tmp_path, ai_mode="gemini", gemini_api_key="test-no-network",
        gemini_free_tier_confirmed=True, ai_requests_per_minute=10, _env_file=None)
    with TestClient(create_app(settings, provider)) as client:
        yield client, provider


def source_draft(client):
    sid = client.post("/api/stories", json={"title": "The remembered river", "genre": "Fantasy", "narrative": "Elara, a quiet village herbalist, found her mother's brass key beside a river that carries memories."}).json()["id"]
    did = client.post(f"/api/stories/{sid}/contributions", json={"text": "A mysterious stranger warns Elara about an approaching disaster.", "expected_version": 1}).json()["id"]
    return sid, did


def generate(client, did, revision=0, request_id=None, panel=None):
    path = f"/api/drafts/{did}/generate" if panel is None else f"/api/drafts/{did}/panels/{panel}/regenerate"
    return client.post(path, json={"request_id": request_id or str(uuid4()), "expected_revision": revision, "consent": True})


def test_generation_context_new_versions_and_publication(ai_client):
    c, provider = ai_client
    sid, original = source_draft(c)
    key = str(uuid4())
    response = generate(c, original, request_id=key)
    assert response.status_code == 200, response.text
    did = response.json()["id"]
    assert did != original
    assert generate(c, original, request_id=key).json()["id"] == did
    assert len(provider.calls) == 1
    draft = c.get(f"/api/drafts/{did}").json()
    assert draft["source"] == "ai_generated" and len(draft["ai_data"]["panels"]) == 2
    assert "quiet village herbalist" in json.dumps(provider.calls[0][1])
    assert "owner_id" not in json.dumps(provider.calls[0][1])
    assert len(c.get(f"/api/stories/{sid}").json()["chapters"]) == 1
    assert c.post(f"/api/drafts/{did}/publish", json={"expected_version": 1, "approved": False}).status_code == 422
    published = c.post(f"/api/drafts/{did}/publish", json={"expected_version": 1, "approved": True})
    assert published.status_code == 200, published.text
    assert c.post(f"/api/drafts/{did}/publish", json={"expected_version": 1, "approved": True}).json() == published.json()
    story = c.get(f"/api/stories/{sid}").json()
    assert len(story["chapters"]) == 2 and len(story["chapters"][-1]["comic_prompts"]) == 2
    snapshot = asyncio.run(c.app.state.repo.context_snapshot(None, sid, []))
    assert snapshot["bible"]["characters"][0]["name"] == "The stranger"
    assert snapshot["outline"][-1]["summary"]["source"] == "ai"
    assert c.get(f"/api/drafts/{original}").json()["status"] == "draft"


def test_regeneration_preserves_draft_and_individual_panels(ai_client):
    c, provider = ai_client
    _, original = source_draft(c)
    did = generate(c, original).json()["id"]
    c.patch(f"/api/drafts/{did}", json={"title": "My saved title", "narrative": chapter_payload()["narrative"]})
    new = generate(c, did, revision=1, panel=0)
    assert new.status_code == 200, new.text
    variant = c.get(f"/api/drafts/{new.json()['id']}").json()
    old = c.get(f"/api/drafts/{did}").json()
    assert old["title"] == variant["title"] == "My saved title"
    assert old["ai_data"]["panels"][1] == variant["ai_data"]["panels"][1]
    assert old["ai_data"]["panels"][0] != variant["ai_data"]["panels"][0]
    assert generate(c, did, revision=1, panel=99).status_code == 422
    regenerated = generate(c, did, revision=1)
    assert regenerated.status_code == 200 and regenerated.json()["id"] not in (did, variant["id"])
    assert c.get(f"/api/drafts/{did}").json()["title"] == "My saved title"


def test_final_edited_text_is_analyzed_before_publish(ai_client):
    c, provider = ai_client
    sid, original = source_draft(c)
    did = generate(c, original).json()["id"]
    c.patch(f"/api/drafts/{did}", json={"title": "Reviewed", "narrative": "Elara declined the stranger's invitation. She would find another way through the forest."})
    response = c.post(f"/api/drafts/{did}/publish", json={"approved": True, "expected_version": 1})
    assert response.status_code == 200, response.text
    assert provider.calls[-1][0] == "analyze_reviewed_chapter"
    assert provider.calls[-1][1]["final_reviewed_chapter"]["title"] == "Reviewed"
    assert c.get(f"/api/stories/{sid}").json()["chapters"][-1]["summary"]["synopsis"] == "Summary of the final reviewed words."


@pytest.mark.parametrize("code,status", [("provider_quota",429),("timeout",504),("invalid_output",502)])
def test_generation_failures_leave_original_and_idea_intact(ai_client, code, status):
    c, p = ai_client
    sid, did = source_draft(c)
    p.error = GenerationError(code, "Temporary generation failure", status)
    response = generate(c, did)
    assert response.status_code == status
    assert c.get(f"/api/drafts/{did}").json()["narrative"].startswith("A mysterious stranger")
    assert len(c.get("/api/drafts").json()) == 1
    assert len(c.get(f"/api/stories/{sid}/chapters").json()) == 1


def test_concurrent_generation_has_one_provider_call(ai_client):
    c, p = ai_client
    _, did = source_draft(c)
    p.release = threading.Event()
    request_id = str(uuid4())
    with ThreadPoolExecutor(2) as pool:
        pending = pool.submit(generate, c, did, 0, request_id)
        assert p.started.wait(5)
        duplicate = generate(c, did, request_id=request_id)
        another = generate(c, did)
        assert duplicate.status_code == another.status_code == 409
        p.release.set()
        assert pending.result().status_code == 200
    assert len(p.calls) == 1


def test_edit_during_generation_rejects_result_without_overwriting(ai_client):
    c, p = ai_client
    _, did = source_draft(c)
    p.release = threading.Event()
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(generate, c, did)
        assert p.started.wait(5)
        edited = "My newer saved idea should survive the in-flight request."
        assert c.patch(f"/api/drafts/{did}", json={"title":"A newer idea","narrative":edited}).status_code == 200
        p.release.set()
        assert pending.result().status_code == 409
    assert c.get(f"/api/drafts/{did}").json()["narrative"] == edited
    assert len(c.get("/api/drafts").json()) == 1


def test_supabase_generation_requires_authentication(tmp_path):
    settings = Settings(app_mode="supabase",supabase_url="https://example.supabase.co",supabase_anon_key="test-public",data_dir=tmp_path,_env_file=None)
    with TestClient(create_app(settings)) as c:
        response = generate(c,str(uuid4()))
        assert response.status_code == 401


def test_quotas_ownership_and_restart(ai_client, tmp_path):
    c, p = ai_client
    _, did = source_draft(c)
    c.app.state.settings.ai_user_daily_limit = 1
    result = generate(c, did)
    assert result.status_code == 200
    assert generate(c, did).status_code == 429
    with TestClient(create_app(c.app.state.settings, FixtureProvider())) as restarted:
        assert restarted.get(f"/api/drafts/{result.json()['id']}").json()["source"] == "ai_generated"
        assert generate(restarted, did).status_code == 429
    with c.app.state.repo.db() as db:
        d = c.app.state.repo.get(db,"drafts",did)
        c.app.state.repo.put(db,"drafts",{**d,"owner_id":PROFILES[1]["id"]})
    assert generate(c,did).status_code == 404


def test_long_context_uses_stored_summaries_and_relevant_excerpts(ai_client):
    c, _ = ai_client
    sid, _ = source_draft(c)
    repo = c.app.state.repo
    with repo.db() as db:
        s = repo.get(db,"stories",sid)
        for i in range(2,35):
            repo.put(db,"chapters",{"id":str(uuid4()),"story_id":sid,"position":i,"title":f"Event {i}","narrative":("The brass compass disappeared. " if i==4 else "The forest grew quieter. ")*300,"summary":{"synopsis":f"Structured memory of event {i}.","source":"extractive"},"author_id":DEMO_USER,"upload_ids":[],"source":"manual","created_at":s["created_at"]})
        repo.put(db,"stories",{**s,"version":34})
    context = asyncio.run(StoryContextBuilder(repo,12000).build(None,sid,"The brass compass returns.","Add a twist"))
    assert len(json.dumps(context).encode()) <= 12000
    assert len(context["recent_relevant_chapters"]) <= 5
    assert context["earlier_summaries"]
    assert any(c["position"]==4 for c in context["recent_relevant_chapters"])
