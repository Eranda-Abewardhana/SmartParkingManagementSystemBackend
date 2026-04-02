from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Smart Parking Management API"
    APP_VERSION: str = "0.1.0"

    # Auth
    SECRET_KEY: Optional[str] = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Database
    DATABASE_URL: Optional[str] = None

    # CORS
    CORS_ALLOW_ORIGINS: List[str] = ["*"]

    # 🔥 FIX: Add HuggingFace token
    HF_TOKEN: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # ✅ prevents crash on unknown env vars
    )


settings = Settings()