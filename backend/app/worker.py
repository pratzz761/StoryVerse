"""Run on the Windows GPU PC: python -m app.worker. Outbound HTTPS only."""
import asyncio
import logging
import os
import json
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID
from urllib.parse import urlparse
import httpx
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from .config import Settings
from .ai.sdxl import LocalSDXLProvider

log = logging.getLogger('storyverse.worker')


@contextmanager
def exclusive_spool(directory):
    """Avoid two local processes racing the same saved result files."""
    directory.mkdir(parents=True, exist_ok=True)
    stream = (directory / '.worker.lock').open('a+b')
    acquired = False
    try:
        if not os.fstat(stream.fileno()).st_size:
            stream.write(b'1'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            raise RuntimeError('Another local worker owns this spool directory') from None
        yield
    finally:
        if acquired:
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def save_record(path, value):
    staged = path.with_suffix('.tmp')
    staged.write_text(json.dumps(value), encoding='utf-8')
    staged.replace(path)


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.worker.env', extra='ignore', hide_input_in_errors=True)
    worker_backend_url: str
    worker_token: str = Field(repr=False, min_length=32)
    worker_id: UUID
    worker_poll_seconds: int = Field(default=5, ge=3, le=30)
    worker_spool_dir: Path = Path('data/worker-spool')

    def validate_endpoint(self):
        endpoint = urlparse(self.worker_backend_url)
        if endpoint.scheme != 'https' or not endpoint.hostname or endpoint.username or endpoint.query or endpoint.fragment or endpoint.path not in ('','/'):
            raise ValueError('Worker backend must be an HTTPS origin without credentials, path or query')


async def once(config, image_settings, client, provider):
    """One job at a time. Retry callbacks with saved PNGs, never rerender them."""
    config.worker_spool_dir.mkdir(parents=True, exist_ok=True)
    pending = list(config.worker_spool_dir.glob('*.json'))
    if pending:
        record = pending[0]
        saved = json.loads(record.read_text(encoding='utf-8'))
        png = record.with_suffix('.png')
    else:
        response = await client.post('/api/worker/claim', params={'worker_id':str(config.worker_id)})
        response.raise_for_status()
        job = response.json()
        if not job:
            return
        saved = {'job_id':str(UUID(job['job_id'])), 'lease':str(UUID(job['lease']))}
        record = config.worker_spool_dir / (saved['job_id']+'.json')
        png = record.with_suffix('.png')
        try:
            for key, value in job['settings'].items():
                if getattr(image_settings, 'sdxl_'+key) != value:
                    raise ValueError('Worker configuration differs from the server')
            # Persist the lease before rendering. On a crash without a PNG, fail
            # the reservation rather than accidentally executing it twice.
            save_record(record, saved)
            image = await provider.generate(job['description'], job['appearance_context'])
            saved['metadata'] = image.metadata
            save_record(record, saved)
            png.write_bytes(image.content)
        except Exception:
            await client.post('/api/worker/jobs/'+saved['job_id']+'/fail', headers={'X-Worker-Lease':saved['lease']})
            record.unlink(missing_ok=True)
            log.warning('Local image job failed; prior draft preserved (details redacted)')
            return
    path = '/api/worker/jobs/'+saved['job_id']
    if not png.exists():
        response = await client.post(path+'/fail', headers={'X-Worker-Lease':saved['lease']})
    else:
        response = await client.post(path+'/complete', content=png.read_bytes(), headers={
            'Content-Type':'image/png', 'X-Worker-Lease':saved['lease'],
            'X-Image-Metadata':json.dumps(saved['metadata'])})
    if response.status_code >= 500 or response.status_code == 429:
        # The next poll retries the exact saved bytes and same lease.
        return
    if response.is_redirect:
        raise RuntimeError('Worker endpoint redirected; configure the final HTTPS origin')
    if response.status_code in (401,403):
        raise RuntimeError('Worker authentication rejected; check backend configuration')
    if response.is_error:
        await client.post(path+'/fail', headers={'X-Worker-Lease':saved['lease']})
        log.warning('Image result was rejected or expired; previous draft preserved')
    record.unlink(missing_ok=True)
    png.unlink(missing_ok=True)


async def run():
    config = WorkerSettings()
    config.validate_endpoint()
    images = Settings(_env_file='.worker.env', app_mode='demo', ai_mode='demo', sdxl_execution='local')
    if not images.sdxl_enabled or images.sdxl_api_flavor != 'comfyui':
        raise ValueError('This worker requires the existing local ComfyUI adapter')
    provider = LocalSDXLProvider(images)
    try:
        with exclusive_spool(config.worker_spool_dir):
            async with httpx.AsyncClient(base_url=config.worker_backend_url, headers={
                    'Authorization':'Bearer '+config.worker_token}, timeout=45, follow_redirects=False, trust_env=False) as client:
                while True:
                    try:
                        await once(config, images, client, provider)
                    except Exception:
                        # No exception chain, headers, prompts, keys or URLs in logs.
                        log.warning('Worker request failed; backing off (details redacted)')
                    await asyncio.sleep(config.worker_poll_seconds)
    finally:
        await provider.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
