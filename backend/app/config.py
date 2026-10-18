from pathlib import Path
from typing import Literal
from pydantic import Field, field_validator
from urllib.parse import urlsplit
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    app_mode: Literal["demo", "supabase"] = "demo"
    app_environment: Literal["development", "production"] = "development"
    public_writes_enabled: bool = True
    moderation_ready: bool = False
    sdxl_execution: Literal["local", "worker"] = "local"
    worker_token: str = Field(default="", repr=False)
    worker_lease_seconds: int = Field(default=300, ge=30, le=300)
    worker_online_seconds: int = Field(default=45, ge=10, le=120)
    supabase_url: str = ""
    supabase_anon_key: str = ""
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    data_dir: Path = Path("data")
    max_upload_bytes: int = 20 * 1024 * 1024
    ai_mode: Literal["demo", "amd", "gemini"] = "demo"
    amd_api_key: str = Field(default="", repr=False)
    amd_model: str = Field(default="DeepSeek-V4-Flash", min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:/-]+$")
    amd_base_url: str = "https://developer.amd.com.cn/radeon/api/v1"
    gemini_api_key: str = Field(default="", repr=False)
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_free_tier_confirmed: bool = False

    @field_validator("amd_base_url")
    @classmethod
    def validate_amd_url(cls, value):
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.port not in (None, 443):
            raise ValueError("AMD_BASE_URL must be an HTTPS API base URL without credentials, query or fragment")
        return value.rstrip("/")
    supabase_service_role_key: str = Field(default="", repr=False)
    ai_timeout_seconds: int = Field(default=45, ge=5, le=90)
    ai_max_input_tokens: int = Field(default=12000, ge=1000, le=16000)
    ai_max_output_tokens: int = Field(default=4096, ge=512, le=6000)
    ai_context_chars: int = Field(default=18000, ge=3000, le=30000)
    ai_user_daily_limit: int = Field(default=10, ge=1, le=100)
    ai_global_daily_limit: int = Field(default=100, ge=1, le=500)
    ai_requests_per_minute: int = Field(default=2, ge=1, le=10)
    ai_global_concurrency: int = Field(default=2, ge=1, le=4)
    sdxl_enabled: bool = False
    sdxl_api_flavor: Literal["a1111", "generic", "comfyui"] = "a1111"
    sdxl_base_url: str = "http://127.0.0.1:7860"
    sdxl_model: str = "sd_xl_base_1.0.safetensors"
    sdxl_width: int = Field(default=768, ge=256, le=1024, multiple_of=64)
    sdxl_height: int = Field(default=768, ge=256, le=1024, multiple_of=64)
    sdxl_steps: int = Field(default=20, ge=1, le=30)
    sdxl_cfg_scale: float = Field(default=6.0, ge=1, le=12)
    sdxl_sampler: str = "DPM++ 2M"
    sdxl_timeout_seconds: int = Field(default=120, ge=10, le=300)
    sdxl_seed: int = Field(default=42, ge=0, le=2147483647)
    sdxl_negative_prompt: str = "blurry, low quality, watermark, text, logo, distorted anatomy"
    # Native ComfyUI names differ from AUTOMATIC1111 sampler labels.
    comfyui_sampler: str = "dpmpp_2m"
    comfyui_scheduler: str = "karras"
    comfyui_poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=5)

    def validate_mode(self):
        if self.supabase_anon_key.startswith('sb_secret_'):
            raise RuntimeError('The public Supabase key field must never contain a secret key.')
        if self.supabase_anon_key.startswith('eyJ'):
            import base64, json
            try:
                part = self.supabase_anon_key.split('.')[1]
                role = json.loads(base64.urlsafe_b64decode(part+'='*(-len(part)%4))).get('role')
            except (ValueError, IndexError):
                role = None
            if role == 'service_role':
                raise RuntimeError('A service-role key must never be configured as a public key.')
        if self.app_mode == "supabase" and not (self.supabase_url and self.supabase_anon_key):
            raise RuntimeError("Supabase mode requires SUPABASE_URL and SUPABASE_ANON_KEY; demo fallback is disabled.")
        if self.sdxl_execution == "worker" and (self.app_mode != "supabase" or not self.supabase_service_role_key or len(self.worker_token) < 32):
            raise RuntimeError("Remote image jobs require Supabase, its backend service key and a worker token of at least 32 characters.")
        if self.app_environment == "production":
            from urllib.parse import urlparse
            def secure(value):
                endpoint = urlparse(value)
                return (endpoint.scheme == "https" and bool(endpoint.hostname)
                    and endpoint.hostname not in ('localhost','127.0.0.1','::1')
                    and not endpoint.username and not endpoint.password and not endpoint.query
                    and not endpoint.fragment and endpoint.path in ('', '/'))
            if self.app_mode != "supabase" or not self.supabase_service_role_key or not secure(self.supabase_url):
                raise RuntimeError("Production requires HTTPS Supabase and its backend service key; local persistence/demo identity is forbidden.")
            if not self.cors_origins or any(not secure(origin) or '*' in origin or urlparse(origin).path not in ('', '/') for origin in self.cors_origins):
                raise RuntimeError("Production requires explicit HTTPS frontend CORS origins.")
            if self.sdxl_enabled and self.sdxl_execution != "worker":
                raise RuntimeError("Cloud deployments must use outbound image workers; PC localhost is not reachable.")
            if self.public_writes_enabled and not self.moderation_ready:
                raise RuntimeError("Assign a moderator and acknowledge MODERATION_READY before enabling public writes.")
