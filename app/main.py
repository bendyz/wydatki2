from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
import os

APP_VERSION = Path("VERSION").read_text().strip()
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Zarządza cyklem życia aplikacji:
    - startup: inicjalizacja bazy danych i uruchomienie schedulera abonamentów
    - shutdown: zatrzymanie schedulera
    """
    # STARTUP
    init_db()

    # Import schedulera tutaj, aby uniknąć circular imports przy imporcie main
    from app.worker.scheduler import shutdown_scheduler, start_scheduler

    start_scheduler()
    print("🚀 Aplikacja Wydatki 2.0 wystartowała. Scheduler abonamentów aktywny.")

    yield

    # SHUTDOWN
    shutdown_scheduler()
    print("🛑 Aplikacja Wydatki 2.0 zamykana. Scheduler zatrzymany.")


app = FastAPI(
    title=settings.app_name,
    description="Aplikacja do zarządzania wydatkami wspierana przez AI.",
    version=APP_VERSION,
    lifespan=lifespan,
)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="templates")
templates.env.globals["js_version"] = str(int(os.path.getmtime("static/js/app.js")))

# CORS — domeny konfigurowane w data/config/config.yaml (klucz allowed_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rejestracja routerów API v1
app.include_router(api_router, prefix="/api/v1")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return RedirectResponse(url="/static/favicon.svg")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "enable_payment_cards": settings.enable_payment_cards,
        "app_version": APP_VERSION,
    })
