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
    registration_enabled: bool = True

    # JWT Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 godziny

    # CORS — domyślnie ["*"] (działa lokalnie i po sklonowaniu repo).
    # Na serwerze produkcyjnym ustaw w config.yaml: allowed_origins: ["https://twoja-domena.pl"]
    allowed_origins: List[str] = Field(default_factory=lambda: ["*"])

    enable_payment_cards: bool = False

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

    def save_to_yaml(self, yaml_path: str = "data/config/config.yaml") -> None:
        data = {
            "app_name": self.app_name,
            "debug": self.debug,
            "registration_enabled": self.registration_enabled,
            "enable_payment_cards": self.enable_payment_cards,
            "SECRET_KEY": self.SECRET_KEY,
            "ALGORITHM": self.ALGORITHM,
            "ACCESS_TOKEN_EXPIRE_MINUTES": self.ACCESS_TOKEN_EXPIRE_MINUTES,
            "server": {"port": self.server.port, "host": self.server.host},
            "database": {"url": self.database.url},
            "storage": {"uploads_path": self.storage.uploads_path},
            "openrouter": {
                "api_key": self.openrouter.api_key,
                "model": self.openrouter.model,
                "max_tokens": self.openrouter.max_tokens,
                "temperature": self.openrouter.temperature,
            },
            "allowed_origins": self.allowed_origins,
            "personal_context": self.personal_context,
            "duplicates": {
                "date_range_days": self.duplicates.date_range_days,
                "amount_threshold": self.duplicates.amount_threshold,
            },
        }
        Path(yaml_path).parent.mkdir(parents=True, exist_ok=True)
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


settings = Settings.from_yaml()
