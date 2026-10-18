import asyncio
import base64
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.ai.providers import ImageProvider, ImageResult, GenerationError
from app.ai.sdxl import LocalSDXLProvider
from tests.test_ai_workflow import FixtureProvider, source_draft, generate
from tests.ai_fixtures import chapter_payload


def png_fixture():
    data = io.BytesIO()
    Image.new("RGB",(768,768),(57,43,78)).save(data,format="PNG")
    return data.getvalue()


class FixtureSDXL(ImageProvider):
    is_test_fixture = True
    def __init__(self):
        self.calls = []
        self.error = None
        self.started = threading.Event()
        self.release = None
    async def generate(self, description, appearance_context):
        self.calls.append((description,appearance_context))
        self.started.set()
        if self.release:
            while not self.release.is_set():
                await asyncio.sleep(.01)
        if self.error:
            raise self.error
        return ImageResult(png_fixture(),"image/png",{"provider":"local_sdxl","model":"sdxl-test-fixture","steps":20,"cfg_scale":6,"sampler":"DPM++ 2M","is_test_fixture":True})


def image_request(client,did,index=0,revision=0,key=None):
    return client.post(f"/api/drafts/{did}/panels/{index}/image",json={"request_id":key or str(uuid4()),"expected_revision":revision,"consent":True})


@pytest.fixture
def sdxl_client(tmp_path):
    image = FixtureSDXL()
    config = Settings(data_dir=tmp_path,ai_mode="gemini",gemini_api_key="test-no-network",gemini_free_tier_confirmed=True,
        sdxl_enabled=True,ai_requests_per_minute=10,_env_file=None)
    with TestClient(create_app(config,FixtureProvider(),image)) as client:
        sid, source = source_draft(client)
        did = generate(client,source).json()["id"]
        yield client,image,sid,did


@pytest.mark.parametrize("flavor",["a1111","generic"])
def test_local_http_contract_and_conservative_settings(flavor):
    seen=[]
    def handler(req):
        seen.append(req)
        if req.url.path.endswith("options"):
            return httpx.Response(200,json={"sd_model_checkpoint":"sd_xl_base_1.0.safetensors [fixture]"})
        if req.url.path.endswith("progress"):
            return httpx.Response(200,json={"state":{"job_count":0}})
        if req.url.path=="/health":
            return httpx.Response(200,json={"family":"sdxl","model":"sd_xl_base_1.0.safetensors","busy":False})
        return httpx.Response(200,json={"images":[base64.b64encode(png_fixture()).decode()]})
    async def run():
        client=httpx.AsyncClient(base_url="http://127.0.0.1:7860",transport=httpx.MockTransport(handler))
        p=LocalSDXLProvider(Settings(sdxl_enabled=True,sdxl_api_flavor=flavor,_env_file=None),client)
        try:
            result=await p.generate(chapter_payload()["panels"][0],{"bible":{},"seed":42})
            import json
            sent=json.loads(seen[-1].content)
            assert sent["batch_size"]==sent["n_iter"]==1
            assert sent["width"]==sent["height"]==768
            assert sent["steps"]==20 and sent["enable_hr"] is False
            assert result.mime_type=="image/png" and result.metadata["seed"]==42
        finally:
            await p.close()
    asyncio.run(run())


@pytest.mark.parametrize("origin",["https://paid.example.com","http://127.0.0.1@remote.example","http://127.0.0.1:7860/?redirect=remote","http://[bad","http://127.0.0.1:999999"])
def test_remote_endpoints_are_rejected_before_http(origin):
    provider=LocalSDXLProvider(Settings(sdxl_enabled=True,sdxl_base_url=origin,_env_file=None))
    with pytest.raises(GenerationError) as error:
        asyncio.run(provider.generate(chapter_payload()["panels"][0],{}))
    assert error.value.code=="invalid_local_endpoint" and provider.client is None


@pytest.mark.parametrize("failure",["unavailable","busy","invalid","mismatch","timeout"])
def test_local_failures_are_bounded_and_never_use_paid_fallback(failure):
    count=0
    def handler(req):
        nonlocal count
        count+=1
        if failure=="timeout": raise httpx.ReadTimeout("fixture",request=req)
        if failure=="unavailable": raise httpx.ConnectError("fixture",request=req)
        if req.url.path.endswith("options"):
            return httpx.Response(200,json={"sd_model_checkpoint":"wrong-model" if failure=="mismatch" else "sd_xl_base_1.0.safetensors"})
        if req.url.path.endswith("progress"):
            return httpx.Response(200,json={"state":{"job_count":1 if failure=="busy" else 0}})
        return httpx.Response(200,json={"images":[base64.b64encode(b"not an image").decode()]})
    async def run():
        p=LocalSDXLProvider(Settings(sdxl_enabled=True,_env_file=None),httpx.AsyncClient(base_url="http://127.0.0.1:7860",transport=httpx.MockTransport(handler)))
        try:
            with pytest.raises(GenerationError):
                await p.generate(chapter_payload()["panels"][0],{})
            assert count<=3
        finally: await p.close()
    asyncio.run(run())


def test_private_images_versions_regeneration_and_publication(sdxl_client):
    c, provider, sid, did=sdxl_client
    key=str(uuid4())
    response=image_request(c,did,key=key)
    assert response.status_code==200,response.text
    image_id=response.json()["id"]
    assert image_request(c,did,key=key).json()["id"]==image_id
    assert len(provider.calls)==1
    new=c.get(f"/api/drafts/{image_id}").json()
    panel=new["ai_data"]["panels"][0]
    assert panel["image"]["is_test_fixture"] and panel["image"]["seed"]==42
    assert not c.get(f"/api/drafts/{did}").json()["ai_data"]["panels"][0].get("image")
    upload_id=panel["image"]["upload_id"]
    with c.app.state.repo.db() as db:
        assert not c.app.state.repo.get(db,"uploads",upload_id)["is_public"]
    second=image_request(c,image_id).json()["id"]
    second_panel=c.get(f"/api/drafts/{second}").json()["ai_data"]["panels"][0]
    assert second_panel["image"]["seed"]==43 and second_panel["image"]["upload_id"]!=upload_id
    assert c.post(f"/api/drafts/{second}/publish",json={"approved":True,"expected_version":1}).status_code==200
    chapter=c.get(f"/api/stories/{sid}").json()["chapters"][-1]
    published_id=chapter["comic_prompts"][0]["image"]["upload_id"]
    with c.app.state.repo.db() as db:
        assert c.app.state.repo.get(db,"uploads",published_id)["is_public"]
        assert not c.app.state.repo.get(db,"uploads",upload_id)["is_public"]
    assert c.get(f"/api/uploads/{published_id}/file").content==png_fixture()


def test_unavailable_runtime_preserves_description_previous_image_and_text(sdxl_client):
    c,p,_,did=sdxl_client
    first=image_request(c,did).json()["id"]
    saved=c.get(f"/api/drafts/{first}").json()
    p.error=GenerationError("sdxl_unavailable","Local SDXL unavailable; descriptions remain available.",503)
    assert image_request(c,first).status_code==503
    after=c.get(f"/api/drafts/{first}").json()
    assert saved["ai_data"]==after["ai_data"]
    assert after["image_generation_error"]=="sdxl_unavailable"
    assert after["narrative"]==saved["narrative"] and after["generation_error"] is None


def test_one_image_at_a_time_and_edit_race(sdxl_client):
    c,p,_,did=sdxl_client
    p.release=threading.Event()
    with ThreadPoolExecutor(1) as pool:
        pending=pool.submit(image_request,c,did)
        assert p.started.wait(5)
        assert image_request(c,did,index=1).status_code==409
        c.patch(f"/api/drafts/{did}",json={"title":"Newer saved text","narrative":"A new reviewed narrative."})
        p.release.set()
        assert pending.result().status_code==409
    assert len(p.calls)==1
    assert c.get(f"/api/drafts/{did}").json()["title"]=="Newer saved text"


def test_images_work_without_gemini_key_and_respect_ownership(sdxl_client):
    c,p,_,did=sdxl_client
    c.app.state.settings.gemini_api_key=""
    assert image_request(c,did).status_code==200
    with c.app.state.repo.db() as db:
        draft=c.app.state.repo.get(db,"drafts",did)
        c.app.state.repo.put(db,"drafts",{**draft,"owner_id":"22222222-2222-4222-8222-222222222222"})
    assert image_request(c,did).status_code==404


def test_description_regeneration_retires_only_its_image_in_new_version(sdxl_client):
    c,p,_,did=sdxl_client
    first=image_request(c,did).json()["id"]
    both=image_request(c,first,index=1).json()["id"]
    saved=c.get(f"/api/drafts/{both}").json()
    result=c.post(f"/api/drafts/{both}/panels/0/regenerate",json={"request_id":str(uuid4()),"expected_revision":0,"consent":True})
    assert result.status_code==200,result.text
    new=c.get(f"/api/drafts/{result.json()['id']}").json()
    assert not new["ai_data"]["panels"][0].get("image")
    assert new["ai_data"]["panels"][1]==saved["ai_data"]["panels"][1]
    assert new["narrative"]==saved["narrative"]
    assert c.get(f"/api/drafts/{both}").json()["ai_data"]==saved["ai_data"]
    assert len(p.calls)==2


def test_disabled_images_preserve_description_without_http(sdxl_client):
    c,p,_,did=sdxl_client
    c.app.state.settings.sdxl_enabled=False
    assert c.get("/api/health").json()["image_generation"]["enabled"] is False
    response=image_request(c,did)
    assert response.status_code==503 and response.json()["code"]=="images_disabled"
    assert not p.calls and len(c.get(f"/api/drafts/{did}").json()["ai_data"]["panels"])==2
