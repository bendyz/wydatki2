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

### Styling — IMPORTANT: shade numbers mean ROLES, not lightness
Dark theme by default, light available via a toggle (persisted in `localStorage`,
falls back to `prefers-color-scheme`). There is no build step (Tailwind Play CDN),
so themes are implemented by **remapping Tailwind's palette onto CSS variables** in
the inline `tailwind.config` in `templates/base.html` — not by rewriting the ~550
color classes across 12 templates and 48 `innerHTML` blocks in `app.js`, and not
with `dark:` variants.

**Shade numbers encode roles, not brightness.** `gray-50` = page background,
`gray-200/300` = borders, `gray-500/600` = labels, `gray-900` = headings; for tinted
scales `-50/100` = chip background, `-200/300` = its hover, `-400..600` = text,
`-700..900` = strong text. In dark the `gray` ramp is **inverted** (`gray-50` is the
darkest); in light it runs normally. Because the roles hold in both, the same markup
works in either theme. Write new markup following the conventions already in the
codebase and it will theme itself.

Theme values live in `static/css/app.css` under `:root` (dark) and
`:root[data-theme="light"]`. The attribute is set by a **blocking inline script in
`<head>` before first paint** — theme logic must not move into `app.js` or you get a
flash of the wrong theme. Charts draw to canvas and don't react to CSS variables, so
`applyTheme()` re-runs `applyChartTheme()` and re-renders the chart-bearing view.

Other conventions that follow from this:
- `bg-white` is not used — cards use `bg-surface` (`white` stays real white because
  `text-white` sits on colored buttons).
- Filled buttons use `bg-primary-solid` / `bg-success-solid` (dark enough for white
  text); `text-primary` / `text-success` are the bright variants for text and icons.
- Modal backdrops use `bg-scrim`, never `bg-gray-500`/`bg-gray-900`.
- Hover on rows and ghost buttons goes *lighter*: `hover:bg-surface-2`.
- `static/css/app.css` holds design tokens as **space-separated RGB channels**
  (`--c-surface: 21 28 46`), consumed by the config as `rgb(var(--c-x) / <alpha-value>)`.
  The Play CDN appends its `<style>` last, so `app.css` can only hold token blocks,
  `@keyframes`, and rules with `!important` or specificity ≥ 0-2-0.
- Category `color` values are stored in the DB and tuned for dark. `readableColor()`
  in `app.js` darkens them at render time in light mode — don't bypass it when
  rendering category dots or chart segments.

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
