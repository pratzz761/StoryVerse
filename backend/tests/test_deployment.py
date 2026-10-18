import asyncio
import copy
import io
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4
import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.ai.providers import GenerationError, ImageResult
from app.ai.remote import RemoteImages
from app.worker import WorkerSettings, once, exclusive_spool

OWNER='11111111-1111-4111-8111-111111111111'
JOB='aaaaaaaa-aaaa-4aaa-8aaa-000000000001'
DRAFT='bbbbbbbb-bbbb-4bbb-8bbb-000000000001'
LEASE='cccccccc-cccc-4ccc-8ccc-000000000001'
TOKEN='synthetic-worker-token-'+'x'*32


def settings(**values):
    return Settings(_env_file=None, **{'app_mode':'supabase','supabase_url':'https://example.supabase.co',
        'supabase_anon_key':'synthetic-anon','supabase_service_role_key':'synthetic-service',
        'sdxl_execution':'worker','sdxl_enabled':True,'worker_token':TOKEN,
        'sdxl_width':256,'sdxl_height':256,**values})


def source():
    return {'id':DRAFT,'owner_id':OWNER,'source':'ai_generated','title':'A chapter','narrative':'The lantern was blue.',
        'ai_data':{'panels':[{'description':'A lantern on a wooden pier at dusk.','location':'Pier','characters':[],'camera':'Wide','caption':''}], 'bible_after':{}}}


def png():
    content=io.BytesIO();Image.new('RGB',(256,256),'purple').save(content,format='PNG');return content.getvalue()


def image_metadata():
    import hashlib
    from app.ai.sdxl import panel_prompt
    return dict(provider='local_sdxl',api_flavor='comfyui',model='sd_xl_base_1.0.safetensors',width=256,height=256,
        steps=20,cfg_scale=6,seed=42,batch_size=1,sampler='dpmpp_2m',scheduler='karras',vae_decode='tiled',workflow_version=1,
        comfyui_prompt_id=JOB,prompt_hash=hashlib.sha256(panel_prompt(source()['ai_data']['panels'][0],{}).encode()).hexdigest(),sha256=hashlib.sha256(png()).hexdigest(),is_test_fixture=False)


@pytest.mark.parametrize('change',[
    {'app_mode':'demo'}, {'cors_origins':['http://insecure.example']},
    {'cors_origins':['https://*.example']}, {'sdxl_execution':'local'},
    {'supabase_service_role_key':''}, {'public_writes_enabled':True,'moderation_ready':False}
])
def test_production_fails_closed(change):
    config=settings(app_environment='production',cors_origins=['https://story.example'],public_writes_enabled=False,**change) if not set(change)&{'cors_origins','public_writes_enabled'} else settings(**{'app_environment':'production','cors_origins':['https://story.example'],'public_writes_enabled':False,**change})
    with pytest.raises(RuntimeError):config.validate_mode()


def test_valid_production_has_no_local_persistence(tmp_path):
    config=settings(app_environment='production',cors_origins=['https://story.example'],public_writes_enabled=False,data_dir=tmp_path/'unused')
    app=create_app(config)
    assert not config.data_dir.exists()
    assert TOKEN not in repr(config)
    asyncio.run(app.state.repo.client.aclose())


def test_unhandled_sdk_exception_never_reaches_server_logs_or_response(caplog):
    app=create_app(settings())
    app.state.repo.authenticate=AsyncMock(return_value=OWNER)
    app.state.repo.profile=AsyncMock(side_effect=RuntimeError('SYNTHETIC_PRIVATE_VALUE_DO_NOT_LOG'))
    with TestClient(app) as client:
        response=client.get('/api/me',headers={'Authorization':'Bearer user'})
        assert response.status_code==500
        assert 'SYNTHETIC_PRIVATE_VALUE_DO_NOT_LOG' not in response.text+caplog.text


def test_worker_and_private_jobs_require_authentication():
    app=create_app(settings())
    app.state.repo.authenticate=AsyncMock(return_value=OWNER)
    app.state.repo.rest=AsyncMock(return_value=[])
    app.state.repo.rpc=AsyncMock(return_value=None)
    with TestClient(app) as client:
        assert client.post('/api/worker/claim',params={'worker_id':JOB}).status_code==401
        assert client.post('/api/worker/claim',params={'worker_id':JOB},headers={'Authorization':'Bearer bad'}).status_code==401
        assert client.post('/api/worker/claim',params={'worker_id':JOB},headers={'Authorization':'Bearer '+TOKEN}).status_code==200
        assert client.get('/api/image-jobs/'+JOB).status_code==401
        assert client.get('/api/image-jobs/'+JOB,headers={'Authorization':'Bearer user'}).status_code==404
        assert app.state.repo.rest.call_args.args[2]['owner_id']=='eq.'+OWNER


def test_offline_worker_does_not_consume_generation_quota():
    repo=NS(generation_source=AsyncMock(return_value=source()),rest=AsyncMock(return_value=[]),rpc=AsyncMock(return_value=False),reserve_generation=AsyncMock())
    with pytest.raises(GenerationError) as error:
        asyncio.run(RemoteImages(settings(),repo).enqueue('user',OWNER,DRAFT,0,JOB,0))
    assert error.value.code=='worker_offline'
    repo.reserve_generation.assert_not_called()


def test_remote_enqueue_is_short_and_replays_when_worker_offline():
    repo=NS(generation_source=AsyncMock(return_value=source()),rest=AsyncMock(return_value=[]),rpc=AsyncMock(return_value=True),
        reserve_generation=AsyncMock(return_value={'id':JOB,'status':'running','claimed':True}),fail_generation=AsyncMock())
    service=RemoteImages(settings(),repo)
    result=asyncio.run(service.enqueue('user',OWNER,DRAFT,0,JOB,0))
    assert result=={'job_id':JOB,'status':'queued'}
    enqueue=repo.rpc.call_args.args
    assert enqueue[0]=='image_enqueue' and enqueue[2]['p_seed']==42
    repo.rest.return_value=[{'id':JOB}];repo.reserve_generation.return_value={'status':'succeeded','result_draft_id':DRAFT}
    repo.rpc.reset_mock()
    assert asyncio.run(service.enqueue('user',OWNER,DRAFT,0,JOB,0))['id']==DRAFT
    repo.rpc.assert_not_called()


def test_remote_completion_validates_png_owner_and_preserves_other_data():
    original=source(); original['ai_data']['panels'].append({'description':'An untouched second panel'})
    snapshot=copy.deepcopy(original)
    async def rpc(name,key,values):
        if name=='image_worker_job':return {'source':snapshot,'panel_index':0,'seed':42,'status':'running'}
        assert name=='image_worker_finish'
        payload=values['p_payload']
        assert payload['title']==original['title'] and payload['panels'][1]==original['ai_data']['panels'][1]
        assert payload['panels'][0]['image']['upload_id']==JOB and not payload['panels'][0]['image']['is_test_fixture']
        return {'id':DRAFT,'replayed':False}
    repo=NS(rpc=AsyncMock(side_effect=rpc),save_worker_upload=AsyncMock(return_value={'id':JOB}))
    service=RemoteImages(settings(),repo)
    assert asyncio.run(service.complete(JOB,LEASE,png(),image_metadata()))['id']==DRAFT
    assert snapshot==original
    assert repo.save_worker_upload.call_args.args[:2]==(OWNER,JOB)
    with pytest.raises(GenerationError):asyncio.run(service.complete(JOB,LEASE,b'not an image',image_metadata()))
    assert repo.save_worker_upload.await_count==1


@pytest.mark.parametrize('changed',[{'seed':99},{'sha256':'f'*64},{'sampler':'other'},{'model':'other'}])
def test_worker_metadata_mismatch_never_saves_a_file(changed):
    repo=NS(rpc=AsyncMock(return_value={'source':source(),'panel_index':0,'seed':42,'status':'running'}),save_worker_upload=AsyncMock())
    with pytest.raises(GenerationError):
        asyncio.run(RemoteImages(settings(),repo).complete(JOB,LEASE,png(),{**image_metadata(),**changed}))
    repo.save_worker_upload.assert_not_called()


def test_production_cors_cache_body_limits_and_pause():
    app=create_app(settings(app_environment='production',cors_origins=['https://story.example'],public_writes_enabled=False))
    app.state.repo.authenticate=AsyncMock(return_value=OWNER)
    with TestClient(app) as client:
        health=client.get('/api/health');assert health.headers['cache-control']=='private, no-store'
        preflight=client.options('/api/stories',headers={'Origin':'https://evil.example','Access-Control-Request-Method':'POST'})
        assert 'access-control-allow-origin' not in preflight.headers
        allowed=client.options('/api/stories',headers={'Origin':'https://story.example','Access-Control-Request-Method':'POST'})
        assert allowed.headers['access-control-allow-origin']=='https://story.example'
        assert client.post('/api/stories',headers={'Authorization':'Bearer user'},json={'title':'A','genre':'Fantasy','narrative':'Opening'}).status_code==503
        assert client.post('/api/stories',content=b'x'*65537).status_code==413


def test_readiness_requires_real_moderator_and_private_bucket():
    app=create_app(settings(app_environment='production',cors_origins=['https://story.example'],moderation_ready=True))
    app.state.repo.rpc=AsyncMock(return_value={'storage_private':True,'moderator_assigned':False})
    with TestClient(app) as client:
        assert client.get('/api/ready').status_code==503
        app.state.repo.rpc.return_value={'storage_private':False,'moderator_assigned':True}
        assert client.get('/api/ready').status_code==503
        app.state.repo.rpc.return_value={'storage_private':True,'moderator_assigned':True}
        assert client.get('/api/ready').status_code==200


def test_modern_supabase_keys_never_become_bearer_tokens_or_leak_to_user_calls():
    from app.supabase import SupabaseRepository
    config=settings(supabase_anon_key='sb_publishable_synthetic',supabase_service_role_key='sb_secret_synthetic')
    repo=SupabaseRepository(config)
    assert repo.headers(None)=={'apikey':'sb_publishable_synthetic'}
    assert repo.headers('user-jwt')=={'apikey':'sb_publishable_synthetic','Authorization':'Bearer user-jwt'}
    assert repo.headers(config.supabase_service_role_key)=={'apikey':'sb_secret_synthetic'}
    asyncio.run(repo.client.aclose())


@pytest.mark.parametrize('key',['sb_secret_synthetic','eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.synthetic'])
def test_privileged_supabase_keys_are_rejected_in_public_configuration(key):
    with pytest.raises(RuntimeError):settings(supabase_anon_key=key).validate_mode()


def test_worker_https_origin_and_credentials_stay_private(tmp_path):
    for endpoint in ['http://example.test','https://user:pass@example.test','https://example.test/path','https://example.test/?token=bad']:
        config=WorkerSettings(_env_file=None,worker_backend_url=endpoint,worker_token=TOKEN,worker_id=JOB)
        with pytest.raises(ValueError):config.validate_endpoint()
    config=WorkerSettings(_env_file=None,worker_backend_url='https://example.test',worker_token=TOKEN,worker_id=JOB)
    assert TOKEN not in repr(config)
    from pydantic import ValidationError
    with pytest.raises(ValidationError) as error:
        WorkerSettings(_env_file=None,worker_backend_url='https://example.test',worker_token='private-short-value',worker_id=JOB)
    assert 'private-short-value' not in str(error.value)


def test_worker_retries_saved_callback_without_another_gpu_render(tmp_path):
    config=WorkerSettings(_env_file=None,worker_backend_url='https://example.test',worker_token=TOKEN,worker_id=JOB,worker_spool_dir=tmp_path)
    images=settings(sdxl_model='sd_xl_base_1.0.safetensors')
    calls=[];completions=0
    def respond(request):
        nonlocal completions
        calls.append(request.url.path)
        if request.url.path.endswith('/claim'):
            return httpx.Response(200,json={'job_id':JOB,'lease':LEASE,'description':source()['ai_data']['panels'][0],
                'appearance_context':{},'settings':{'model':images.sdxl_model,'width':256,'height':256,'steps':20,'cfg_scale':6}})
        assert request.headers['x-worker-lease']==LEASE
        completions+=1
        return httpx.Response(503 if completions==1 else 200,json={'id':DRAFT})
    provider=NS(generate=AsyncMock(return_value=ImageResult(png(),'image/png',{})))
    async def run():
        async with httpx.AsyncClient(base_url='https://example.test',transport=httpx.MockTransport(respond)) as client:
            await once(config,images,client,provider)
            assert len(list(tmp_path.glob('*.png')))==1
            await once(config,images,client,provider)
    asyncio.run(run())
    assert provider.generate.await_count==1 and calls.count('/api/worker/claim')==1
    assert not list(tmp_path.iterdir())


def test_only_one_local_process_can_own_the_worker_spool(tmp_path):
    with exclusive_spool(tmp_path):
        with pytest.raises(RuntimeError):
            with exclusive_spool(tmp_path):
                pass
    with exclusive_spool(tmp_path):
        pass
