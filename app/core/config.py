import os
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    port: int = 8000
    host: str = "0.0.0.0"


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///data/db/wydatki.db"


class StorageConfig(BaseModel):
    uploads_path: str = "data/uploads/receipts"


class OpenRouterConfig(BaseModel):
    api_key: str = ""
    model: str = "moonshotai/kimi-k2.6"
    max_tokens: int = 4096
    temperature: float = 0.1


class DuplicatesConfig(BaseModel):
    date_range_days: int = 3
    amount_threshold: float = 0.5


class Settings(BaseModel):
    """Konfiguracja aplikacji ładowana z YAML z możliwością nadpisania przez zmienne środowiskowe."""

    app_name: str = "Wydatki 2.0"
    debug: bool = True

    # JWT Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 godziny

    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    openrouter: OpenRouterConfig = Field(default_factory=OpenRouterConfig)
    personal_context: List[str] = Field(default_factory=list)
    duplicates: DuplicatesConfig = Field(default_factory=DuplicatesConfig)

    @classmethod
    def from_yaml(cls, yaml_path: str = "data/config/config.yaml") -> "Settings":
        path = Path(yaml_path)
        if not path.exists():
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Nadpisania ze zmiennych środowiskowych (priorytet nad YAML)
        env_api_key = os.getenv("OPENROUTER_API_KEY")
        if env_api_key:
            data.setdefault("openrouter", {})["api_key"] = env_api_key

        env_db_url = os.getenv("DATABASE_URL")
        if env_db_url:
            data.setdefault("database", {})["url"] = env_db_url

        env_port = os.getenv("PORT")
        if env_port:
            data.setdefault("server", {})["port"] = int(env_port)

        return cls(**data)


settings = Settings.from_yaml()
