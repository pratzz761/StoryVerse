"""HTTP contract tests; no credentials, external network or Gemini fallback."""
import asyncio
import copy
import json
from unittest.mock import patch
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.ai.amd import AMDProvider, amd_response_schema
from app.ai.providers import GeminiProvider, GenerationError
from app.ai.schemas import GeneratedChapter, MemoryOutput, ComicPrompt
from tests.ai_fixtures import chapter_payload
from tests.test_ai_workflow import source_draft, generate, FixtureProvider


def settings(**kwargs):
    return Settings(ai_mode="amd", amd_api_key="synthetic-amd-key", _env_file=None, **kwargs)


def catalog(**kwargs):
    return {"data": [{"id": "DeepSeek-V4-Flash", "free": True, "json_output": True,
        "structured_outputs": True, "context_length": 1048576, **kwargs}]}


def completion(payload=None, **kwargs):
    return {"model": "DeepSeek-V4-Flash", "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload or chapter_payload())}}],
        "usage": {"prompt_tokens": 1800, "completion_tokens": 700}, **kwargs}


def provider(handler, **kwargs):
    return AMDProvider(settings(**kwargs), httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_schema_requires_nested_fields_and_keeps_local_bounds():
    wire = amd_response_schema(GeneratedChapter)
    character = wire["$defs"]["Character"]
    assert character["required"] == list(character["properties"])
    assert "default" not in character["properties"]["visual_description"]
    assert wire["properties"]["panels"]["minItems"] == 2
    assert wire["additionalProperties"] is False


@pytest.mark.parametrize("structured", [True, False])
def test_documented_http_auth_catalog_cache_and_structured_formats(structured):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer synthetic-amd-key"
        assert str(request.url).startswith("https://developer.amd.com.cn/radeon/api/v1/")
        if request.method == "GET":
            return httpx.Response(200, json=catalog(structured_outputs=structured))
        body = json.loads(request.content)
        assert body["model"] == "DeepSeek-V4-Flash" and body["stream"] is False
        assert body["max_tokens"] == 4096 and "tools" not in body
        assert body["messages"][0]["role"] == "system"
        assert "untrusted contextual DATA" in body["messages"][0]["content"]
        assert "synthetic-amd-key" not in request.content.decode()
        assert body["response_format"]["type"] == ("json_schema" if structured else "json_object")
        return httpx.Response(200, json=completion())
    p = provider(handler)
    async def run():
        for _ in range(2):
            result = await p.structured("continue_story", {"contributor_idea": "A flood warning."}, GeneratedChapter)
            assert result.model == "DeepSeek-V4-Flash" and result.input_tokens == 1800
            assert len(result.value.panels) == 2
        await p.close()
    asyncio.run(run())
    assert [r.method for r in calls] == ["GET", "POST", "POST"]


@pytest.mark.parametrize("status,code", [(400,"provider_unavailable"),(401,"provider_auth"),(403,"provider_auth"),(429,"provider_quota"),(503,"provider_unavailable"),(307,"provider_unavailable")])
def test_errors_do_not_retry_or_call_gemini(status, code):
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json=catalog()) if request.method == "GET" else httpx.Response(status, json={"error":"synthetic-amd-key"})
    p = provider(handler)
    with patch("google.genai.Client") as gemini, pytest.raises(GenerationError) as error:
        asyncio.run(p.structured("continue_story", {}, GeneratedChapter))
    assert error.value.code == code and "synthetic-amd-key" not in str(error.value)
    assert calls == ["GET", "POST"]
    gemini.assert_not_called()


@pytest.mark.parametrize("model", [{"free":False},{"id":"retired"},{"json_output":False}])
def test_paid_retired_or_non_json_models_never_generate(model):
    calls = []
    p = provider(lambda r: (calls.append(r.method), httpx.Response(200, json=catalog(**model)))[1])
    with pytest.raises(GenerationError) as error:
        asyncio.run(p.structured("continue_story", {}, GeneratedChapter))
    assert error.value.code == "model_unavailable" and calls == ["GET"]


@pytest.mark.parametrize("mutation,code", [
    (lambda r: r.update(choices=[]), "invalid_output"),
    (lambda r: r["choices"][0].update(message=None), "invalid_output"),
    (lambda r: r["choices"][0]["message"].update(content="```json\n{}\n```"), "invalid_output"),
    (lambda r: r["choices"][0]["message"].update(content=json.dumps({**chapter_payload(), "panels":[]})), "invalid_output"),
    (lambda r: r["choices"][0].update(finish_reason="length"), "output_limit"),
    (lambda r: r["choices"][0].update(finish_reason="content_filter"), "blocked"),
    (lambda r: r["choices"][0]["message"].update(refusal="cannot comply"), "blocked"),
    (lambda r: r["usage"].update(completion_tokens=6001), "output_limit"),
    (lambda r: r.update(model="another-model"), "invalid_output"),
    (lambda r: r.update(usage={}), "invalid_output"),
])
def test_incomplete_blocked_and_invalid_results_are_rejected(mutation, code):
    output = completion()
    mutation(output)
    p = provider(lambda r: httpx.Response(200, json=catalog() if r.method == "GET" else output))
    with pytest.raises(GenerationError) as error:
        asyncio.run(p.structured("continue_story", {}, GeneratedChapter))
    assert error.value.code == code


def test_input_budget_and_timeout():
    calls = []
    def handler(r):
        calls.append(r.method)
        if r.method == "GET": return httpx.Response(200, json=catalog())
        raise httpx.ReadTimeout("synthetic-amd-key")
    p = provider(handler)
    with pytest.raises(GenerationError) as error:
        asyncio.run(p.structured("continue_story", {"idea":"x"*16000}, GeneratedChapter))
    assert error.value.code == "context_limit" and calls == ["GET"]
    with pytest.raises(GenerationError) as error:
        asyncio.run(p.structured("continue_story", {}, GeneratedChapter))
    assert error.value.code == "timeout" and "synthetic-amd-key" not in str(error.value)


@pytest.mark.parametrize("case", ["network", "bad_catalog", "oversized"])
def test_transport_and_response_bounds(case):
    def handler(request):
        if case == "network": raise httpx.ConnectError("synthetic-amd-key")
        if case == "bad_catalog": return httpx.Response(200, json={"data":None})
        if request.method == "GET": return httpx.Response(200, json=catalog())
        return httpx.Response(200, content=b"x"*262145)
    p = provider(handler)
    with pytest.raises(GenerationError) as error:
        asyncio.run(p.structured("continue_story", {}, GeneratedChapter))
    assert error.value.code == ("network" if case == "network" else "invalid_output")
    assert "synthetic-amd-key" not in str(error.value)


def test_selection_missing_key_environment_and_url_validation(monkeypatch):
    monkeypatch.setenv("AMD_API_KEY", "synthetic-environment-amd")
    s = Settings(_env_file=None)
    assert s.amd_api_key == "synthetic-environment-amd"
    assert "synthetic-environment-amd" not in repr(s)
    from app.ai.service import AIService
    assert isinstance(AIService(settings(), None).provider, AMDProvider)
    assert isinstance(AIService(Settings(ai_mode="gemini", _env_file=None), None).provider, GeminiProvider)
    s = Settings(ai_mode="amd", amd_api_key="", gemini_api_key="synthetic-fallback-key", gemini_free_tier_confirmed=True, _env_file=None)
    assert not AIService(s, None).status()["enabled"]
    with pytest.raises(GenerationError) as error:
        asyncio.run(AMDProvider(s).structured("continue_story", {}, GeneratedChapter))
    assert error.value.code == "not_configured"
    for url in ["http://example.com", "https://key@example.com", "https://example.com?key=secret"]:
        with pytest.raises(ValueError): settings(amd_base_url=url)


def test_examples_keep_amd_key_blank_and_server_side():
    root = Path(__file__).resolve().parents[2]
    for file in [root / "backend/.env.example", root / "backend/.env.production.example"]:
        keys = [line for line in file.read_text(encoding="utf-8").splitlines() if line.startswith("AMD_API_KEY=")]
        assert len(keys) == 1
        present = bool(keys[0].partition("=")[2].strip())
        assert not present, "AMD credentials must stay outside templates (value redacted)"
    for file in (root / "frontend/src").rglob("*.ts*"):
        assert "AMD_API_KEY" not in file.read_text(encoding="utf-8")


def test_mocked_amd_chapter_panel_memory_versioning_and_publication(tmp_path):
    tasks = []
    def handler(request):
        if request.method == "GET": return httpx.Response(200, json=catalog())
        data = json.loads(request.content)
        task = json.loads(data["messages"][1]["content"])["task"]
        tasks.append(task)
        value = copy.deepcopy(chapter_payload())
        if task == "regenerate_single_panel_description": value = value["panels"][0]
        if task == "analyze_reviewed_chapter": value = value["memory"]
        return httpx.Response(200, json=completion(value))
    s = settings(data_dir=tmp_path, ai_requests_per_minute=10)
    p = AMDProvider(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    p.is_test_fixture = True
    with TestClient(create_app(s, p)) as c:
        sid, did = source_draft(c)
        generated = generate(c, did)
        assert generated.status_code == 200
        result = c.get('/api/drafts/'+generated.json()["id"]).json()
        assert result["ai_data"]["provider"] == "amd"
        assert result["ai_data"]["model"] == "DeepSeek-V4-Flash"
        regenerated = generate(c, result["id"], panel=0)
        assert regenerated.status_code == 200
        final = regenerated.json()["id"]
        assert c.patch(f"/api/drafts/{final}", json={"title":"Reviewed AMD title", "narrative":result["narrative"]}).status_code == 200
        published = c.post(f"/api/drafts/{final}/publish", json={"expected_version":1,"approved":True})
        assert published.status_code == 200
        assert c.post(f"/api/drafts/{final}/publish", json={"expected_version":1,"approved":True}).json() == published.json()
        assert len(c.get(f"/api/stories/{sid}").json()["chapters"]) == 2
        assert c.get(f"/api/drafts/{did}").json()["source"] == "demo_preview"
        final_draft = c.get(f"/api/drafts/{final}").json()
        assert final_draft["ai_data"]["memory_provider"] == "amd"
    assert tasks == ["continue_story", "regenerate_single_panel_description", "analyze_reviewed_chapter"]


def test_explicit_gemini_review_keeps_amd_narrative_provenance(tmp_path):
    s = settings(data_dir=tmp_path, ai_requests_per_minute=10)
    p = provider(lambda r: httpx.Response(200, json=catalog() if r.method == "GET" else completion()))
    with TestClient(create_app(s, p)) as c:
        _, original = source_draft(c)
        did = generate(c, original).json()["id"]
        c.patch(f"/api/drafts/{did}", json={"title":"My final title", "narrative":chapter_payload()["narrative"]})
        # Simulate the explicit operator selection on the shared persisted draft.
        s.ai_mode = "gemini"
        s.gemini_api_key = "synthetic-gemini-key"
        s.gemini_free_tier_confirmed = True
        c.app.state.ai.provider = FixtureProvider()
        response = c.post(f"/api/drafts/{did}/publish", json={"expected_version":1,"approved":True})
        assert response.status_code == 200
        data = c.get(f"/api/drafts/{did}").json()["ai_data"]
        assert data["provider"] == "amd" and data["model"] == "DeepSeek-V4-Flash"
        assert data["memory_provider"] == "gemini" and data["memory_model"] == "gemini-test-fixture"
    asyncio.run(p.close())
