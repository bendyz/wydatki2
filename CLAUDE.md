# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the application
python run.py

# Run with uvicorn directly (hot reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Install dependencies
pip install -r requirements.txt

# Interactive API docs (when server is running)
# http://localhost:8000/docs
```

There are no tests in this project.

## Architecture

**Wydatki 2.0** is a Polish personal expense tracker with AI-powered receipt scanning. FastAPI backend serves both a REST API and a Jinja2-rendered SPA frontend.

### Stack
- **Backend**: FastAPI, SQLAlchemy 2.0 (sync), SQLite via `aiosqlite`
- **Frontend**: Jinja2 templates (`templates/`) + vanilla JS (`static/js/app.js`) — single-page feel served from `GET /`
- **AI**: OpenRouter API (LLM + vision) — configured in `data/config/config.yaml`
- **Image processing**: OpenCV (`image_service.py`) converts receipt photos to grayscale + adaptive threshold before sending to AI
- **Background jobs**: APScheduler (`app/worker/scheduler.py`) runs daily at midnight to generate expenses from due subscriptions

### Configuration
All settings live in `data/config/config.yaml` (loaded by `app/core/config.py`). Three env vars override YAML: `OPENROUTER_API_KEY`, `DATABASE_URL`, `PORT`. The SQLite database is at `data/db/wydatki.db`. Receipt images are stored under `data/uploads/receipts/<expense_id>/`.

### Data model
Five SQLAlchemy models in `app/models/models.py`:
- `User` → owns `Expense`, `Subscription`, `Category`
- `Category` — can be user-scoped or global (`user_id` nullable)
- `Expense` → has optional `ExpenseItem` line items and optional `receipt_image_path`
- `Subscription` — tracks `frequency_days`, `next_billing_date`, `remaining_installments`; scheduler converts due ones into `Expense` rows

### API structure
All REST endpoints under `/api/v1/` (registered in `app/api/v1/router.py`):
- `/auth` — register, login (returns JWT), `/me`
- `/categories`, `/expenses`, `/subscriptions`, `/stats` — standard CRUD
- `/receipts` — attach/retrieve images for an existing expense
- `/ai/receipt` — upload image → OpenCV processing → OpenRouter vision → returns `ExpenseDraft` (not saved)
- `/ai/text` — natural language description → OpenRouter LLM → returns `ExpenseDraft` (not saved)

### AI draft flow
Both AI endpoints return `ExpenseDraft` (schema in `app/schemas/ai_draft.py`) for user confirmation — nothing is persisted automatically. The draft includes duplicate-detection warnings (checked in `ai_service._check_duplicates` against expenses ±3 days with amount within 0.5 PLN threshold). The caller must explicitly `POST /expenses` to save.

### Auth pattern
`get_current_user` dependency lives in `app/api/v1/endpoints/auth.py`. Import it from there in new endpoints — do not re-implement JWT decoding elsewhere.

### Personal context
`personal_context` in `config.yaml` is a list of user-specific facts injected into every AI system prompt (e.g., car name, home city, card names). Add new facts there to improve categorization without touching code.

### API spec (for Android / external clients)
Full OpenAPI 3.1 spec is exported to `docs/api.json`. Regenerate after any API change:
```bash
python scripts/export_openapi.py
```
The spec covers all endpoints, request/response schemas, and auth (Bearer JWT). When working on the Android app, read `docs/api.json` instead of running the server.
