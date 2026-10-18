"""Credential-free regression tests. Synthetic values never reach a live SDK."""
import asyncio
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.ai.providers import GeminiProvider, GenerationError
from app.ai.schemas import GeneratedChapter


def test_gemini_key_is_loaded_from_backend_environment_and_hidden_in_repr(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-environment-fixture")
    settings = Settings(_env_file=None)
    assert settings.gemini_api_key == "synthetic-environment-fixture"
    assert "synthetic-environment-fixture" not in repr(settings)


def test_missing_key_does_not_construct_or_call_live_sdk(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = Settings(ai_mode="gemini", gemini_free_tier_confirmed=True, _env_file=None)
    assert settings.gemini_api_key == ""
    with patch("google.genai.Client") as sdk:
        with pytest.raises(GenerationError) as error:
            asyncio.run(GeminiProvider(settings).structured("continue_story", {}, GeneratedChapter))
        assert error.value.code == "not_configured"
        sdk.assert_not_called()


def test_missing_key_keeps_app_usable_and_contribution_saved(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = Settings(data_dir=tmp_path, app_mode="demo", ai_mode="gemini", gemini_free_tier_confirmed=True, _env_file=None)
    with patch("google.genai.Client") as sdk, TestClient(create_app(settings)) as client:
        health = client.get("/api/health").json()
        assert health["ai_enabled"] is False
        sid = client.post("/api/stories", json={"title":"Without a key","genre":"Fantasy","narrative":"A small door appeared by the river."}).json()["id"]
        did = client.post(f"/api/stories/{sid}/contributions", json={"text":"A traveler knocks on the door.","expected_version":1}).json()["id"]
        response = client.post(f"/api/drafts/{did}/generate", json={"request_id":"aaaaaaaa-aaaa-4aaa-8aaa-000000000001","expected_revision":0,"consent":True})
        assert response.status_code == 503
        assert response.json()["code"] == "not_configured"
        assert client.get(f"/api/drafts/{did}").json()["narrative"] == "A traveler knocks on the door."
        assert len(client.get(f"/api/stories/{sid}/chapters").json()) == 1
        sdk.assert_not_called()


def test_example_contains_only_one_blank_gemini_key():
    template = Path(__file__).resolve().parents[1] / ".env.example"
    assignments = [line for line in template.read_text(encoding="utf-8").splitlines() if line.strip().startswith("GEMINI_API_KEY=")]
    assignment_count = len(assignments)
    assert assignment_count == 1, "Document the Gemini key exactly once (values redacted)"
    # Assert on a boolean so pytest's rewritten failure cannot echo a credential.
    key_present = bool(assignments[0].partition("=")[2].strip())
    assert not key_present, "Keep real credentials out of .env.example (value redacted)"
