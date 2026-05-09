from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.endpoints.auth import get_current_admin
from app.core.config import settings

router = APIRouter()


class AdminConfigSchema(BaseModel):
    app_name: str
    debug: bool
    registration_enabled: bool
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    server_host: str
    server_port: int
    database_url: str
    storage_uploads_path: str
    openrouter_api_key: str
    openrouter_model: str
    openrouter_max_tokens: int
    openrouter_temperature: float
    personal_context: List[str]
    duplicates_date_range_days: int
    duplicates_amount_threshold: float


def _settings_to_schema() -> AdminConfigSchema:
    return AdminConfigSchema(
        app_name=settings.app_name,
        debug=settings.debug,
        registration_enabled=settings.registration_enabled,
        SECRET_KEY=settings.SECRET_KEY,
        ACCESS_TOKEN_EXPIRE_MINUTES=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        server_host=settings.server.host,
        server_port=settings.server.port,
        database_url=settings.database.url,
        storage_uploads_path=settings.storage.uploads_path,
        openrouter_api_key=settings.openrouter.api_key,
        openrouter_model=settings.openrouter.model,
        openrouter_max_tokens=settings.openrouter.max_tokens,
        openrouter_temperature=settings.openrouter.temperature,
        personal_context=settings.personal_context,
        duplicates_date_range_days=settings.duplicates.date_range_days,
        duplicates_amount_threshold=settings.duplicates.amount_threshold,
    )


@router.get("/config", response_model=AdminConfigSchema, summary="Pobierz konfigurację")
def get_config(_=Depends(get_current_admin)):
    return _settings_to_schema()


@router.put("/config", response_model=AdminConfigSchema, summary="Zapisz konfigurację")
def update_config(data: AdminConfigSchema, _=Depends(get_current_admin)):
    settings.app_name = data.app_name
    settings.debug = data.debug
    settings.registration_enabled = data.registration_enabled
    settings.SECRET_KEY = data.SECRET_KEY
    settings.ACCESS_TOKEN_EXPIRE_MINUTES = data.ACCESS_TOKEN_EXPIRE_MINUTES
    settings.server.host = data.server_host
    settings.server.port = data.server_port
    settings.database.url = data.database_url
    settings.storage.uploads_path = data.storage_uploads_path
    settings.openrouter.api_key = data.openrouter_api_key
    settings.openrouter.model = data.openrouter_model
    settings.openrouter.max_tokens = data.openrouter_max_tokens
    settings.openrouter.temperature = data.openrouter_temperature
    settings.personal_context = data.personal_context
    settings.duplicates.date_range_days = data.duplicates_date_range_days
    settings.duplicates.amount_threshold = data.duplicates_amount_threshold
    settings.save_to_yaml()
    return _settings_to_schema()
