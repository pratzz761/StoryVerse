"""Native ComfyUI HTTP and application integration. No network/GPU/credentials."""
import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.ai.providers import GenerationError
from app.ai.sdxl import LocalSDXLProvider, MAX_IMAGE_BYTES
from tests.ai_fixtures import chapter_payload
from tests.test_ai_workflow import FixtureProvider, source_draft, generate
from tests.test_sdxl import png_fixture, image_request


class ComfyFixture:
    """Models the queue -> accepted -> pending -> completed -> PNG protocol."""
    def __init__(self):
        self.requests = []
        self.prompts = []
        self.polls = 0
        self.pending_polls = 1
        self.queue = {"queue_running": [], "queue_pending": []}
        self.submit_override = None
        self.history_override = None
        self.view_status = 200
        self.content = png_fixture()
        self.image = {"filename": "ComfyUI_temp_fixture_00001_.png", "subfolder": "", "type": "temp"}
        self.started = threading.Event()
        self.release = None

    async def handle(self, request):
        self.requests.append(request)
        if request.url.path == "/queue":
            return httpx.Response(200, json=self.queue)
        if request.url.path == "/prompt":
            assert request.method == "POST"
            if self.submit_override is not None:
                return self.submit_override
            self.prompts.append(json.loads(request.content))
            self.prompt_id = str(uuid4())
            self.polls = 0
            self.started.set()
            return httpx.Response(200, json={"prompt_id": self.prompt_id, "number": 0, "node_errors": {}})
        if request.url.path == f"/history/{self.prompt_id}":
            self.polls += 1
            if self.release:
                while not self.release.is_set():
                    await asyncio.sleep(.01)
            if self.history_override is not None:
                return httpx.Response(200, json=self.history_override)
            if self.polls <= self.pending_polls:
                return httpx.Response(200, json={})
            return httpx.Response(200, json={self.prompt_id: {"status": {"status_str": "success", "completed": True, "messages": []},
                "outputs": {"7": {"images": [self.image]}}}})
        if request.url.path == "/view":
            assert request.method == "GET"
            assert dict(request.url.params) == self.image
            return httpx.Response(self.view_status, content=self.content, headers={"content-type": "image/png"})
        raise AssertionError(f"Unexpected endpoint: {request.method} {request.url.path}")


def provider_for(runtime, **overrides):
    settings = Settings(sdxl_enabled=True, sdxl_api_flavor="comfyui", sdxl_base_url="http://127.0.0.1:8188",
        comfyui_poll_interval_seconds=.1, _env_file=None, **overrides)
    provider = LocalSDXLProvider(settings, httpx.AsyncClient(base_url=settings.sdxl_base_url, transport=httpx.MockTransport(runtime.handle)))
    provider.is_test_fixture = True
    return provider


def render(runtime, **overrides):
    async def run():
        provider = provider_for(runtime, **overrides)
        try:
            return await provider.generate(chapter_payload()["panels"][0], {
                "bible": {"characters": [{"name": "Elara", "description": "A quiet herbalist with a brass key."}]}, "seed": 47})
        finally:
            await provider.close()
    return asyncio.run(run())


def test_native_workflow_polling_retrieval_and_conservative_settings():
    runtime = ComfyFixture()
    result = render(runtime)
    graph = runtime.prompts[0]["prompt"]
    assert graph["1"]["inputs"]["ckpt_name"] == "sd_xl_base_1.0.safetensors"
    assert graph["4"]["inputs"] == {"width": 768, "height": 768, "batch_size": 1}
    sampler = graph["5"]["inputs"]
    assert sampler["steps"] == 20 and sampler["seed"] == 47 and sampler["sampler_name"] == "dpmpp_2m"
    assert sampler["scheduler"] == "karras" and sampler["denoise"] == 1
    assert graph["6"]["class_type"] == "VAEDecodeTiled"
    assert graph["7"]["class_type"] == "PreviewImage"
    assert sum(n["class_type"] == "CheckpointLoaderSimple" for n in graph.values()) == 1
    assert sum(n["class_type"] == "KSampler" for n in graph.values()) == 1
    assert "brass key" in graph["2"]["inputs"]["text"]
    assert graph["3"]["inputs"]["text"]
    assert [r.url.path for r in runtime.requests] == ["/queue", "/prompt", f"/history/{runtime.prompt_id}", f"/history/{runtime.prompt_id}", "/view"]
    assert result.content == png_fixture() and result.mime_type == "image/png"
    assert result.metadata["api_flavor"] == "comfyui" and result.metadata["comfyui_prompt_id"] == runtime.prompt_id
    assert result.metadata["sampler"] == "dpmpp_2m" and result.metadata["scheduler"] == "karras"
    assert result.metadata["vae_decode"] == "tiled" and result.metadata["is_test_fixture"]


def test_comfyui_environment_configuration(monkeypatch):
    monkeypatch.setenv("SDXL_API_FLAVOR", "comfyui")
    monkeypatch.setenv("COMFYUI_SAMPLER", "euler")
    monkeypatch.setenv("COMFYUI_SCHEDULER", "normal")
    monkeypatch.setenv("COMFYUI_POLL_INTERVAL_SECONDS", "2")
    settings = Settings(_env_file=None)
    assert settings.sdxl_api_flavor == "comfyui" and settings.comfyui_poll_interval_seconds == 2
    runtime = ComfyFixture()
    result = render(runtime)
    assert runtime.prompts[0]["prompt"]["5"]["inputs"]["sampler_name"] == "euler"
    assert result.metadata["sampler"] == "euler" and result.metadata["scheduler"] == "normal"


def test_partial_outputs_are_not_retrieved_before_successful_completion():
    runtime = ComfyFixture()
    runtime.pending_polls = 0
    original = runtime.handle
    async def handle(request):
        response = await original(request)
        if request.url.path.startswith("/history/") and runtime.polls == 1:
            return httpx.Response(200, json={runtime.prompt_id: {
                "status": {"status_str": "success", "completed": False},
                "outputs": {"7": {"images": [runtime.image]}}}})
        return response
    runtime.handle = handle
    render(runtime)
    assert runtime.polls == 2
    assert [r.url.path for r in runtime.requests].count("/view") == 1


def test_image_retrieval_does_not_follow_redirects():
    runtime = ComfyFixture()
    runtime.pending_polls = 0
    original = runtime.handle
    async def handle(request):
        if request.url.path == "/view":
            runtime.requests.append(request)
            return httpx.Response(302, headers={"location": "https://remote.example/image.png"})
        return await original(request)
    runtime.handle = handle
    with pytest.raises(GenerationError) as error:
        render(runtime)
    assert error.value.code == "sdxl_unavailable"
    assert all(r.url.host == "127.0.0.1" for r in runtime.requests)


@pytest.mark.parametrize("queue", [
    {"queue_running": [[0, "other-job"]], "queue_pending": []},
    {"queue_running": [], "queue_pending": [[1, "other-job"]]},
    {"queue_running": [], "queue_pending": None},
])
def test_busy_or_invalid_queue_never_submits(queue):
    runtime = ComfyFixture()
    runtime.queue = queue
    with pytest.raises(GenerationError) as error:
        render(runtime)
    assert error.value.code in {"sdxl_busy", "sdxl_unavailable"}
    assert len(runtime.requests) == 1 and not runtime.prompts


@pytest.mark.parametrize("response", [
    httpx.Response(400, json={"error": {"message": "private raw workflow/path"}}),
    httpx.Response(200, json={"node_errors": {"1": {"errors": ["private checkpoint/path"]}}}),
    httpx.Response(200, json={"error": "private raw workflow"}),
    httpx.Response(200, json={"prompt_id": "../../remote"}),
])
def test_submission_failures_are_sanitized_and_not_retried(response):
    runtime = ComfyFixture()
    runtime.submit_override = response
    with pytest.raises(GenerationError) as error:
        render(runtime)
    assert "private" not in str(error.value)
    assert [r.url.path for r in runtime.requests] == ["/queue", "/prompt"]


@pytest.mark.parametrize("status", [
    {"status_str": "error", "completed": False, "messages": [["execution_error", {"exception_message": "private CUDA traceback"}]]},
    {"status_str": "success", "completed": False, "messages": [["execution_interrupted", {}]]},
])
def test_failed_or_interrupted_execution_never_fetches_image(status):
    runtime = ComfyFixture()
    original = runtime.handle
    async def handle(request):
        response = await original(request)
        if request.url.path.startswith("/history/"):
            return httpx.Response(200, json={runtime.prompt_id: {"status": status, "outputs": {}}})
        return response
    runtime.handle = handle
    with pytest.raises(GenerationError) as error:
        render(runtime)
    assert error.value.code == "sdxl_execution_failed" and "private" not in str(error.value)
    assert not any(r.url.path == "/view" for r in runtime.requests)


@pytest.mark.parametrize("reference", [
    {"filename": "../private.png", "type": "temp"},
    {"filename": "image.png", "subfolder": "../private", "type": "output"},
    {"filename": "image.png", "subfolder": "C:\\private", "type": "temp"},
    {"filename": "https://remote/image.png", "type": "output"},
    {"filename": "image.png", "type": "input"},
])
def test_invalid_image_references_never_fetch_arbitrary_files(reference):
    runtime = ComfyFixture()
    runtime.pending_polls = 0
    runtime.image = reference
    with pytest.raises(GenerationError) as error:
        render(runtime)
    assert error.value.code == "invalid_image"
    assert not any(r.url.path == "/view" for r in runtime.requests)


@pytest.mark.parametrize("outputs", [{}, {"7": {"images": []}}, {"7": {"images": [{}, {}]}}, {"8": {"images": [{}]}}])
def test_missing_or_multiple_output_images_are_rejected(outputs):
    runtime = ComfyFixture()
    original = runtime.handle
    async def handle(request):
        response = await original(request)
        if request.url.path.startswith("/history/"):
            return httpx.Response(200, json={runtime.prompt_id: {"status": {"status_str": "success", "completed": True}, "outputs": outputs}})
        return response
    runtime.handle = handle
    with pytest.raises(GenerationError) as error:
        render(runtime)
    assert error.value.code == "invalid_image"
    assert not any(r.url.path == "/view" for r in runtime.requests)


@pytest.mark.parametrize("case", ["invalid", "missing", "oversized"])
def test_bad_missing_or_oversized_png_preserves_failure_contract(case):
    runtime = ComfyFixture()
    runtime.pending_polls = 0
    runtime.content = b"x" * (MAX_IMAGE_BYTES + 1) if case == "oversized" else b"not a PNG"
    runtime.view_status = 404 if case == "missing" else 200
    with pytest.raises(GenerationError) as error:
        render(runtime)
    assert error.value.code in {"invalid_image", "sdxl_unavailable"}
    assert len(runtime.prompts) == 1


def test_overall_timeout_bounds_pending_polling_without_resubmission():
    runtime = ComfyFixture()
    runtime.history_override = {}  # Pending indefinitely, including an evicted/missing job.
    provider = provider_for(runtime)
    # Shorten only the test deadline; production configuration has a 10s minimum.
    provider.settings = provider.settings.model_copy(update={"sdxl_timeout_seconds": .025})
    async def run():
        try:
            with pytest.raises(GenerationError) as error:
                await provider.generate(chapter_payload()["panels"][0], {})
            assert error.value.code == "sdxl_timeout"
        finally:
            await provider.close()
    asyncio.run(run())
    assert len(runtime.prompts) == 1
    assert not any(r.url.path in {"/view", "/interrupt"} for r in runtime.requests)


def test_native_adapter_reuses_private_upload_versioning_regeneration_and_publication(tmp_path):
    runtime = ComfyFixture()
    runtime.pending_polls = 0
    provider = provider_for(runtime)
    settings = provider.settings.model_copy(update={"data_dir": tmp_path, "ai_mode": "gemini",
        "gemini_api_key": "synthetic-no-network", "gemini_free_tier_confirmed": True, "ai_requests_per_minute": 10})
    with TestClient(create_app(settings, FixtureProvider(), provider)) as client:
        sid, source = source_draft(client)
        draft = generate(client, source).json()["id"]
        key = str(uuid4())
        response = image_request(client, draft, key=key)
        assert response.status_code == 200, response.text
        first = response.json()["id"]
        assert image_request(client, draft, key=key).json()["id"] == first
        assert len(runtime.prompts) == 1
        saved = client.get(f"/api/drafts/{first}").json()
        image = saved["ai_data"]["panels"][0]["image"]
        assert image["api_flavor"] == "comfyui" and image["is_test_fixture"]
        with client.app.state.repo.db() as db:
            assert not client.app.state.repo.get(db, "uploads", image["upload_id"])["is_public"]
        # Regenerate one image; preserve other prompts and the previous version.
        second = image_request(client, first).json()["id"]
        regenerated = client.get(f"/api/drafts/{second}").json()
        assert regenerated["parent_draft_id"] == first
        assert regenerated["ai_data"]["panels"][1] == saved["ai_data"]["panels"][1]
        assert regenerated["ai_data"]["panels"][0]["image"]["seed"] == image["seed"] + 1
        assert regenerated["narrative"] == saved["narrative"]
        # A later execution failure keeps the existing image and description.
        runtime.submit_override = httpx.Response(400, json={"error": "fixture checkpoint unavailable"})
        assert image_request(client, second).status_code == 503
        assert client.get(f"/api/drafts/{second}").json()["ai_data"] == regenerated["ai_data"]
        assert client.post(f"/api/drafts/{second}/publish", json={"approved": True, "expected_version": 1}).status_code == 200
        chapter = client.get(f"/api/stories/{sid}").json()["chapters"][-1]
        published_image = chapter["comic_prompts"][0]["image"]
        assert published_image["api_flavor"] == "comfyui"
        assert client.get(f"/api/uploads/{published_image['upload_id']}/file").content == png_fixture()
        with client.app.state.repo.db() as db:
            assert client.app.state.repo.get(db, "uploads", published_image["upload_id"])["is_public"]
            assert not client.app.state.repo.get(db, "uploads", image["upload_id"])["is_public"]


def test_comfyui_polling_holds_existing_image_lock_and_rejects_edit_race(tmp_path):
    runtime = ComfyFixture()
    runtime.pending_polls = 0
    runtime.release = threading.Event()
    provider = provider_for(runtime)
    settings = provider.settings.model_copy(update={"data_dir": tmp_path, "ai_mode": "gemini",
        "gemini_api_key": "synthetic-no-network", "gemini_free_tier_confirmed": True, "ai_requests_per_minute": 10})
    with TestClient(create_app(settings, FixtureProvider(), provider)) as client:
        _, source = source_draft(client)
        draft = generate(client, source).json()["id"]
        with ThreadPoolExecutor(1) as pool:
            pending = pool.submit(image_request, client, draft)
            try:
                assert runtime.started.wait(5)
                assert image_request(client, draft, index=1).status_code == 409
                assert client.patch(f"/api/drafts/{draft}", json={"title": "Saved newer title", "narrative": "Newer reviewed words."}).status_code == 200
            finally:
                runtime.release.set()
            assert pending.result(timeout=5).status_code == 409
        assert len(runtime.prompts) == 1
        assert client.get(f"/api/drafts/{draft}").json()["title"] == "Saved newer title"
