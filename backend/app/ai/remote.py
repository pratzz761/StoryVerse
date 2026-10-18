"""Durable outbound-worker bridge. The cloud never contacts a PC endpoint."""
import copy
import hashlib
from uuid import UUID
from fastapi import HTTPException
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from .providers import GenerationError
from .schemas import narrative_hash
from .sdxl import validate_png, panel_prompt


class WorkerImageMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider: Literal['local_sdxl']
    api_flavor: Literal['comfyui']
    model: str = Field(max_length=200)
    width: int
    height: int
    steps: int
    cfg_scale: float
    seed: int
    batch_size: Literal[1]
    sampler: str = Field(max_length=80)
    scheduler: str = Field(max_length=80)
    vae_decode: Literal['tiled']
    workflow_version: Literal[1]
    comfyui_prompt_id: UUID
    prompt_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    is_test_fixture: Literal[False]


class RemoteImages:
    def __init__(self, settings, repo):
        self.settings, self.repo = settings, repo

    async def rpc(self, name, values):
        return await self.repo.rpc(name, self.settings.supabase_service_role_key, values)

    async def enqueue(self, token, owner, draft_id, index, request_id, revision):
        source = await self.repo.generation_source(token, owner, draft_id)
        panels = source.get('ai_data', {}).get('panels', [])
        if source.get('source') != 'ai_generated' or not 0 <= index < len(panels):
            raise HTTPException(422, 'Generate panel descriptions first')
        existing = await self.repo.rest('generation_jobs', token, {'owner_id':f'eq.{owner}', 'request_id':f'eq.{request_id}', 'select':'id'})
        if not existing:
            online = await self.rpc('image_worker_online', {'p_seconds':self.settings.worker_online_seconds})
            if not online:
                raise GenerationError('worker_offline', 'The local image worker is offline. Descriptions and previous images are safe; retry when it reconnects.', 503, 30)
        signature = hashlib.sha256(f'{draft_id}:image:{revision}:{index}'.encode()).hexdigest()
        job = await self.repo.reserve_generation(token, owner, draft_id, request_id, 'image', revision, signature, self.settings)
        if job['status'] == 'succeeded':
            return {'id':job['result_draft_id'], 'replayed':True}
        if job['status'] == 'failed':
            raise GenerationError('image_failed', 'This image attempt failed; your previous draft is safe. Retry explicitly.', 409)
        if job.get('claimed'):
            panel = panels[index]
            seed = (int(panel.get('image', {}).get('seed', self.settings.sdxl_seed + index - 1)) + 1) % 2147483647
            try:
                await self.rpc('image_enqueue', {'p_job':job['id'], 'p_source':source, 'p_index':index, 'p_seed':seed,
                    'p_settings':{k:getattr(self.settings, 'sdxl_'+k) for k in ('model','width','height','steps','cfg_scale')}})
            except Exception:
                await self.repo.fail_generation(token, owner, job['id'], 'queue_unavailable')
                raise
        return {'job_id':job['id'], 'status':'queued'}

    async def status(self, token, owner, job_id):
        jobs = await self.repo.rest('generation_jobs', token, {'id':f'eq.{job_id}', 'owner_id':f'eq.{owner}', 'select':'id,status,result_draft_id,error_code,expires_at'})
        if not jobs:
            raise HTTPException(404, 'Image job not found')
        job = jobs[0]
        from datetime import datetime, timezone
        if job['status'] == 'running' and datetime.fromisoformat(job['expires_at'].replace('Z','+00:00')) <= datetime.now(timezone.utc):
            await self.repo.fail_generation(token, owner, job_id, 'worker_timeout')
            job.update(status='failed', error_code='worker_timeout')
        return {'job_id':job['id'], 'status':job['status'], 'id':job.get('result_draft_id'),
            'code':job.get('error_code'), 'detail':'The worker did not finish. Your previous draft and descriptions are preserved.' if job['status']=='failed' else None}

    async def complete(self, job_id, lease, content, metadata):
        UUID(lease)
        job = await self.rpc('image_worker_job', {'p_job':job_id, 'p_lease':lease})
        if job['status'] == 'succeeded':
            return {'id':job['result_draft_id'], 'replayed':True}
        width, height = validate_png(content, self.settings.sdxl_width, self.settings.sdxl_height)
        source, index = job['source'], job['panel_index']
        meta = WorkerImageMetadata.model_validate(metadata).model_dump(mode='json')
        expected = {'model':self.settings.sdxl_model,'width':width,'height':height,
            'steps':self.settings.sdxl_steps,'cfg_scale':self.settings.sdxl_cfg_scale,'seed':job['seed'],
            'sampler':self.settings.comfyui_sampler,'scheduler':self.settings.comfyui_scheduler,
            'sha256':hashlib.sha256(content).hexdigest()}
        expected['prompt_hash'] = hashlib.sha256(panel_prompt(source['ai_data']['panels'][index],
            source['ai_data'].get('bible_after', {})).encode()).hexdigest()
        if any(meta[key] != value for key,value in expected.items()):
            raise GenerationError('invalid_image', 'Worker image metadata does not match its reservation')
        if len(content) > self.settings.max_upload_bytes:
            raise GenerationError('invalid_image', 'Worker image exceeds the upload limit')
        # Fixed job UUID makes callback retries use one storage identity. The
        # worker never receives user JWTs, service-role keys or Storage credentials.
        upload = await self.repo.save_worker_upload(source['owner_id'], job_id, content)
        payload = copy.deepcopy(source['ai_data'])
        payload.update(title=source['title'], narrative=source['narrative'])
        payload['panels'][index]['image'] = {**meta,'upload_id':upload['id'], 'provider':'local_sdxl',
            'model':self.settings.sdxl_model, 'width':width, 'height':height, 'steps':self.settings.sdxl_steps,
            'seed':job['seed'], 'api_flavor':'comfyui', 'transport':'outbound_worker', 'batch_size':1,
            'sha256':hashlib.sha256(content).hexdigest(), 'mime_type':'image/png', 'is_test_fixture':False}
        payload['memory_revision'] = 0 if payload.get('memory_hash') == narrative_hash(source['title'], source['narrative']) else -1
        return await self.rpc('image_worker_finish', {'p_job':job_id, 'p_lease':lease, 'p_payload':payload})
