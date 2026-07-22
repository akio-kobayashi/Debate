from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma4:31b")
    ollama_num_ctx: int = int(os.getenv("OLLAMA_NUM_CTX", "32768"))
    ollama_timeout_seconds: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))
    debate_max_chars: int = int(os.getenv("DEBATE_MAX_CHARS", "500"))
    bind_host: str = os.getenv("DEBATE_BIND_HOST", "0.0.0.0")
    port: int = int(os.getenv("DEBATE_PORT", "8000"))
    overlay_provider: str = os.getenv("OVERLAY_PROVIDER", "none").lower()
    google_form_id: str = os.getenv("GOOGLE_FORM_ID", "")
    google_drive_folder_id: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    google_oauth_client_secrets: str = os.getenv(
        "GOOGLE_OAUTH_CLIENT_SECRETS", ""
    )
    google_oauth_token: str = os.getenv("GOOGLE_OAUTH_TOKEN", "")


settings = Settings()
