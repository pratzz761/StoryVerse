from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4
import hmac
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import Settings
from .demo import DemoRepository
from .models import ContributionCreate, DraftUpdate, GenerationRequest, Genre, ProfileUpdate, PublishRequest, StoryCreate, InteractionSet, ReadingUpdate, ContentReport, ModerationDecision
from .ai.service import AIService
from .ai.providers import GenerationError
from .ai.images import PanelImageService
from .seed import DEMO_USER
from .supabase import SupabaseRepository
from .ai.remote import RemoteImages
from .security import RequestSafety

bearer = HTTPBearer(auto_error=False)
MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4", "audio/webm", "video/mp4", "video/webm"}


def valid_signature(mime, data):
    if mime == "image/jpeg": return data.startswith(b"\xff\xd8\xff")
    if mime == "image/png": return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/gif": return data.startswith((b"GIF87a", b"GIF89a"))
    if mime == "image/webp": return data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if mime == "audio/wav": return data.startswith(b"RIFF") and data[8:12] == b"WAVE"
    if mime == "audio/ogg": return data.startswith(b"OggS")
    if mime in ("video/mp4", "audio/mp4"): return data[4:8] == b"ftyp"
    if mime in ("video/webm", "audio/webm"): return data.startswith(b"\x1a\x45\xdf\xa3")
    if mime == "audio/mpeg": return data.startswith(b"ID3") or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)
    return False


def create_app(settings: Settings | None = None, ai_provider=None, image_provider=None):
    config = settings or Settings()
    config.validate_mode()
    repo = SupabaseRepository(config) if config.app_mode == "supabase" else DemoRepository(config.data_dir)
    ai = AIService(config, repo, ai_provider)
    images = PanelImageService(config, repo, image_provider)
    remote = RemoteImages(config, repo) if config.sdxl_execution == "worker" else None

    @asynccontextmanager
    async def lifespan(app):
        yield
        await ai.provider.close()
        await images.provider.close()
        if isinstance(repo, SupabaseRepository):
            await repo.client.aclose()

    app = FastAPI(title="StoryVerse API", version="0.3.0", lifespan=lifespan)
    app.state.ai = ai
    app.state.images = images
    app.state.repo = repo
    app.state.settings = config
    app.state.remote = remote
    app.add_middleware(RequestSafety, max_upload_bytes=config.max_upload_bytes, production=config.app_environment == "production")
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins,
        allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])

    async def optional_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        if config.app_mode == "demo":
            return {"id": DEMO_USER, "token": None}
        if credentials is None:
            return {"id": None, "token": None}
        return {"id": await repo.authenticate(credentials.credentials), "token": credentials.credentials}

    async def required_user(request: Request, user=Depends(optional_user)):
        if not user["id"]:
            raise HTTPException(401, "Sign in to contribute")
        if request.method in ("POST", "PATCH") and not config.public_writes_enabled and not request.url.path.startswith('/api/moderation/') and not request.url.path.endswith('/reports'):
            raise HTTPException(503, "Writing is temporarily paused. Reading and saved content remain available.")
        return user

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        import logging
        from fastapi.responses import JSONResponse
        # Exception chains can include provider URLs/credentials. Never log them.
        logging.getLogger(__name__).error("Unexpected API error")
        return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})

    @app.exception_handler(GenerationError)
    async def generation_error(request: Request, exc: GenerationError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status, content={"detail": str(exc), "code": exc.code},
            headers={"Retry-After": str(exc.retry_after)} if exc.retry_after else {})

    @app.get("/api/health")
    async def health():
        ai_info = {**ai.status(), "images": "local_sdxl" if images.status()["enabled"] else "descriptions_only"}
        return {"status": "ok", "mode": config.app_mode, "ai_enabled": ai_info["enabled"], "ai": ai_info,
            "image_generation": images.status(), "storage": "supabase" if config.app_mode == "supabase" else "local-sqlite"}

    @app.get("/api/ready")
    async def readiness():
        if config.app_environment != 'production':
            return {'ready':True, 'production':False}
        from fastapi.responses import JSONResponse
        try:
            state = await repo.rpc('deployment_ready', config.supabase_service_role_key, {})
            ready = state.get('storage_private') and (not config.public_writes_enabled or state.get('moderator_assigned'))
        except HTTPException:
            ready = False
        return JSONResponse({'ready':bool(ready)}, status_code=200 if ready else 503)

    @app.get("/api/me")
    async def me(user=Depends(required_user)):
        return await repo.profile(user["token"], user["id"])

    @app.patch("/api/me")
    async def update_me(values: ProfileUpdate, user=Depends(required_user)):
        return await repo.update_profile(user["token"], user["id"], values.model_dump())

    @app.get("/api/profiles/{user_id}")
    async def profile(user_id: UUID, user=Depends(optional_user)):
        return await repo.profile(user["token"], str(user_id))

    @app.get("/api/me/stories")
    async def my_stories(user=Depends(required_user)):
        return await repo.user_stories(user["token"], user["id"])

    @app.get("/api/stories")
    async def stories(search: str = Query(default="", max_length=100), genre: Genre | None = None,
        sort: Literal["trending", "recent"] = "trending", user=Depends(optional_user)):
        return await repo.list_stories(user["token"], search, genre, sort)

    @app.post("/api/stories", status_code=201)
    async def create_story(values: StoryCreate, user=Depends(required_user)):
        return await repo.create_story(user["token"], user["id"], values.model_dump(mode="json"))

    @app.get("/api/discover")
    async def discover(search: str = Query(default="", max_length=100), genre: Genre | None = None,
        sort: Literal["trending", "recent"] = "trending", page: int = Query(default=1, ge=1, le=100000),
        page_size: int = Query(default=12, ge=1, le=60), user=Depends(optional_user)):
        return await repo.discover(user["token"], search, genre, sort, page, page_size)

    @app.get("/api/stories/{story_id}/engagement")
    async def engagement(story_id: UUID, user=Depends(optional_user)):
        return await repo.engagement(user["token"], user["id"], str(story_id))

    @app.post("/api/stories/{story_id}/interactions")
    async def interaction(story_id: UUID, values: InteractionSet, user=Depends(required_user)):
        return await repo.set_interaction(user["token"], user["id"], str(story_id), values.kind, values.active)

    @app.get("/api/me/reading/{story_id}")
    async def reading(story_id: UUID, user=Depends(required_user)):
        return await repo.reading_progress(user["token"], user["id"], str(story_id))

    @app.post("/api/me/reading/{story_id}")
    async def save_reading(story_id: UUID, values: ReadingUpdate, user=Depends(required_user)):
        return await repo.save_reading_progress(user["token"], user["id"], str(story_id), values.model_dump(mode="json"))

    @app.get("/api/stories/{story_id}/bible")
    async def bible(story_id: UUID, user=Depends(optional_user)):
        return await repo.story_bible(user["token"], str(story_id))

    @app.get("/api/stories/{story_id}")
    async def story(story_id: UUID, user=Depends(optional_user)):
        return await repo.story(user["token"], str(story_id))

    @app.get("/api/stories/{story_id}/chapters")
    async def chapters(story_id: UUID, user=Depends(optional_user)):
        return (await repo.story(user["token"], str(story_id)))["chapters"]

    @app.post("/api/stories/{story_id}/contributions", status_code=201)
    async def contribute(story_id: UUID, values: ContributionCreate, user=Depends(required_user)):
        return await repo.create_contribution(user["token"], user["id"], str(story_id), values.model_dump(mode="json"))

    @app.get("/api/drafts")
    async def drafts(user=Depends(required_user)):
        return await repo.list_drafts(user["token"], user["id"])

    @app.get("/api/drafts/{draft_id}")
    async def draft(draft_id: UUID, user=Depends(required_user)):
        return await repo.draft(user["token"], user["id"], str(draft_id))

    @app.patch("/api/drafts/{draft_id}")
    async def update_draft(draft_id: UUID, values: DraftUpdate, user=Depends(required_user)):
        return await repo.update_draft(user["token"], user["id"], str(draft_id), values.model_dump())

    @app.post("/api/drafts/{draft_id}/regenerate")
    async def regenerate(draft_id: UUID, user=Depends(required_user)):
        return await repo.regenerate(user["token"], user["id"], str(draft_id))

    @app.post("/api/drafts/{draft_id}/publish")
    async def publish(draft_id: UUID, values: PublishRequest, user=Depends(required_user)):
        await ai.prepare_publish(user["token"], user["id"], str(draft_id), values.expected_version)
        return await repo.publish(user["token"], user["id"], str(draft_id), values.expected_version)

    @app.post("/api/drafts/{draft_id}/generate")
    async def generate(draft_id: UUID, values: GenerationRequest, user=Depends(required_user)):
        return await ai.generate(user["token"], user["id"], str(draft_id), str(values.request_id), values.expected_revision)

    @app.post("/api/drafts/{draft_id}/panels/{panel_index}/regenerate")
    async def regenerate_panel(draft_id: UUID, panel_index: int, values: GenerationRequest, user=Depends(required_user)):
        return await ai.generate(user["token"], user["id"], str(draft_id), str(values.request_id), values.expected_revision, panel_index)

    @app.post("/api/drafts/{draft_id}/panels/{panel_index}/image")
    async def generate_panel_image(draft_id: UUID, panel_index: int, values: GenerationRequest, user=Depends(required_user)):
        if remote:
            from fastapi.responses import JSONResponse
            if not config.sdxl_enabled:
                raise GenerationError("images_disabled", "Image generation is disabled; panel descriptions remain available.", 503)
            result = await remote.enqueue(user["token"], user["id"], str(draft_id), panel_index, str(values.request_id), values.expected_revision)
            return JSONResponse(result, status_code=202 if result.get("job_id") else 200)
        return await images.generate(user["token"], user["id"], str(draft_id), panel_index, str(values.request_id), values.expected_revision)

    @app.get("/api/image-jobs/{job_id}")
    async def image_job(job_id: UUID, user=Depends(required_user)):
        if not remote:
            raise HTTPException(404, "Remote image jobs are not enabled")
        return await remote.status(user["token"], user["id"], str(job_id))

    async def worker_auth(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        if not remote or not config.sdxl_enabled or not credentials or not hmac.compare_digest(credentials.credentials, config.worker_token):
            raise HTTPException(401, "Invalid worker authentication")

    @app.post("/api/worker/claim", dependencies=[Depends(worker_auth)])
    async def worker_claim(worker_id: UUID):
        return await remote.rpc("image_worker_claim", {"p_worker":str(worker_id), "p_lease_seconds":config.worker_lease_seconds})

    @app.post("/api/worker/jobs/{job_id}/complete", dependencies=[Depends(worker_auth)])
    async def worker_complete(job_id: UUID, request: Request, x_worker_lease: Annotated[UUID, Header()], x_image_metadata: Annotated[str, Header(max_length=8192)]):
        if request.headers.get("content-type") != "image/png":
            raise HTTPException(415, "Worker callbacks must contain a PNG")
        try:
            from .ai.remote import WorkerImageMetadata
            from pydantic import ValidationError
            try:
                metadata = WorkerImageMetadata.model_validate_json(x_image_metadata).model_dump(mode='json')
            except ValidationError:
                raise HTTPException(422, "Invalid worker metadata")
            return await remote.complete(str(job_id), str(x_worker_lease), await request.body(), metadata)
        except GenerationError as exc:
            await remote.rpc("image_worker_fail", {"p_job":str(job_id),"p_lease":str(x_worker_lease),"p_code":exc.code})
            raise

    @app.post("/api/worker/jobs/{job_id}/fail", dependencies=[Depends(worker_auth)])
    async def worker_fail(job_id: UUID, x_worker_lease: Annotated[UUID, Header()]):
        # No raw worker exception text, filesystem paths or prompt data accepted.
        await remote.rpc("image_worker_fail", {"p_job":str(job_id),"p_lease":str(x_worker_lease),"p_code":"worker_failed"})
        return {"status":"failed"}

    def hosted_only():
        if config.app_mode != "supabase":
            raise HTTPException(503, "Public reports and moderation require hosted accounts")

    @app.post("/api/stories/{story_id}/reports", status_code=201)
    async def report_story(story_id: UUID, values: ContentReport, user=Depends(required_user)):
        hosted_only()
        return await repo.rpc("report_story", user["token"], {"p_story":str(story_id),"p_reason":values.reason,"p_details":values.details})

    @app.get("/api/moderation/reports")
    async def reports(user=Depends(required_user)):
        hosted_only()
        return await repo.rpc("moderation_reports", user["token"], {})

    @app.post("/api/moderation/stories/{story_id}")
    async def moderate(story_id: UUID, values: ModerationDecision, user=Depends(required_user)):
        hosted_only()
        return await repo.rpc("moderate_story", user["token"], {"p_story":str(story_id),"p_hidden":values.hidden,"p_reason":values.reason})

    @app.post("/api/uploads", status_code=201)
    async def upload(file: Annotated[UploadFile, File()], user=Depends(required_user)):
        try:
            if file.content_type not in MIME_TYPES:
                raise HTTPException(415, "Choose a JPEG, PNG, WebP, GIF, MP3, WAV, OGG, MP4, or WebM file")
            content = bytearray()
            while chunk := await file.read(1024 * 1024):
                content.extend(chunk)
                if len(content) > config.max_upload_bytes:
                    raise HTTPException(413, "Files must be 20 MB or smaller")
            if not valid_signature(file.content_type, content):
                raise HTTPException(415, "The file content does not match its media type")
            filename = Path((file.filename or "attachment").replace("\\", "/")).name[:150]
            return await repo.save_upload(user["token"], user["id"], str(uuid4()), filename, file.content_type, bytes(content), config.data_dir)
        finally:
            await file.close()

    @app.get("/api/uploads/{upload_id}/file")
    async def read_file(upload_id: UUID, user=Depends(optional_user)):
        item = await repo.get_upload(user["token"], user["id"], str(upload_id))
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
        if config.app_mode == "demo":
            path = config.data_dir / "uploads" / str(upload_id)
            if not path.is_file():
                raise HTTPException(404, "File not found")
            return FileResponse(path, media_type=item["mime_type"], headers=headers)
        return Response(await repo.read_upload(user["token"], item), media_type=item["mime_type"], headers=headers)

    return app


app = create_app()
