"""Runtime settings, read from environment variables (or a .env file)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "repcheck"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:4b"
    # DEMO SHIM (revert after the promo video): "openai" stands in for Ollama when no local model is available.
    llm_provider: str = "ollama"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    coach_password: str = "change-me"
    cookie_secure: bool = False
    frontend_url: str = "http://localhost:3000"
    max_upload_mb: int = 100
    upload_dir: str = "uploads"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    demo_seed_on_start: bool = False
    model_dir: str = str(BACKEND_DIR / "models")
    max_video_seconds: int = 60
    overlay_ttl_days: int = 7

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        if not p.is_absolute():
            p = BACKEND_DIR / p
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
