# Phase 2 — REST API (FastAPI)

## Goal

Expose the crawler as a web service. Instead of running `python main.py`
directly, Phase 2 wraps the crawler behind a REST API so it can be
triggered, monitored, and queried over HTTP.

This also introduces the first **persistent storage** — PostgreSQL to
store every crawled page as a durable record instead of printing to stdout.

---

## What Was Built

```
Phase 1                          Phase 2
──────────────────────────       ──────────────────────────────────────
python main.py (script)    →     FastAPI server (always-on)
print() output             →     PostgreSQL (durable records)
hardcoded SEED_URLS        →     POST /crawl  (trigger via API)
no query capability        →     GET  /search, GET /pages
```

**Status: ✅ Complete**

---

## Folder Structure

```
.
├── api/
│   ├── main.py          ← FastAPI app, mounts all routers, auto-creates tables on startup
│   ├── schemas.py       ← Pydantic request/response models
│   ├── routes/
│   │   ├── crawl.py     ← POST /api/v1/crawl, GET /api/v1/crawl/status
│   │   ├── pages.py     ← GET /api/v1/pages, GET /api/v1/pages/{id}
│   │   └── health.py    ← GET /health
│   └── db/
│       ├── session.py   ← SQLAlchemy engine + session factory (get_db dependency)
│       └── models.py    ← ORM models (Page table)
├── crawler/             ← Phase 1 code (unchanged — imported as-is)
│   ├── main.py
│   ├── fetcher.py
│   ├── parser.py
│   └── frontier.py
├── requirements.txt     ← All dependencies (Phase 1 + Phase 2)
├── setup_db.sql         ← Manual SQL for DB/table creation
└── PHASE_2_API.md
```

---

## API Endpoints

| Method | Endpoint | What it does |
|---|---|---|
| `POST` | `/api/v1/crawl` | Start a crawl with given seed URLs + page limit |
| `GET` | `/api/v1/crawl/status` | Return crawl stats (pages crawled, queue size, domain breakdown) |
| `GET` | `/api/v1/pages` | List all crawled pages (paginated) |
| `GET` | `/api/v1/pages/{id}` | Get a single page record by ID |
| `GET` | `/health` | Liveness check — returns `{"status": "ok"}` |

### Request / Response examples

**POST /api/v1/crawl**
```json
// Request
{ "seed_urls": ["https://example.com"], "max_pages": 50 }

// Response
{ "message": "Crawl completed", "seed_count": 1, "max_pages": 50, "pages_crawled": 42 }
```

**GET /api/v1/crawl/status**
```json
{
  "pages_crawled": 42,
  "pages_failed": 3,
  "queue_size": 112,
  "unique_urls_seen": 305,
  "domain_breakdown": {
    "example.com": 42
  }
}
```

**GET /api/v1/pages**
```json
[
  {
    "id": 1,
    "url": "https://example.com",
    "title": "Example Domain",
    "http_status": 200,
    "crawl_status": "success",
    "crawled_at": "2026-09-28T09:00:00Z"
  }
]
```

---

## PostgreSQL Schema

```sql
CREATE TABLE pages (
    id           SERIAL PRIMARY KEY,
    url          TEXT UNIQUE NOT NULL,
    title        TEXT,
    http_status  INTEGER,
    crawl_status TEXT,        -- 'success' | 'failed' | 'skipped'
    crawled_at   TIMESTAMPTZ DEFAULT now()
);
```

Every crawl attempt writes one row. Failed URLs are also recorded (with
`crawl_status = 'failed'`) so we know what was attempted. Re-crawling a URL
updates the existing row via `INSERT … ON CONFLICT DO UPDATE` (upsert).

---

## How to Run

```bash
# 1. Install all dependencies
pip install -r requirements.txt

# 2. Create the PostgreSQL database
psql -U postgres -c "CREATE DATABASE crawlerdb;"

# 3. Set the connection string
# Windows PowerShell:
$env:DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@localhost:5432/crawlerdb"
# macOS/Linux:
export DATABASE_URL="postgresql://postgres:YOUR_PASSWORD@localhost:5432/crawlerdb"

# 4. Start the server (tables are auto-created on startup)
uvicorn api.main:app --reload

# 5. Open Swagger UI
# http://127.0.0.1:8000/docs
```

---

## Step-by-Step Build Record

### Step 1 — FastAPI skeleton ✅
- Created `api/main.py` with a bare FastAPI app using `lifespan` context
- Added `/health` endpoint in `api/routes/health.py`
- `uvicorn api.main:app --reload` starts the server

### Step 2 — Connect PostgreSQL ✅
- Created `api/db/session.py` — engine + `SessionLocal` + `get_db()` FastAPI dependency
- Created `api/db/models.py` — `Page` ORM model (SQLAlchemy 2.x `Mapped` style)
- `Base.metadata.create_all()` on app startup auto-creates the table (no manual SQL needed for dev)

### Step 3 — Wire crawler into POST /crawl ✅
- Phase 1 crawl loop refactored into `routes/crawl.py`
- After each fetch: `_upsert_page()` writes/updates a row via `INSERT … ON CONFLICT DO UPDATE`
- Crawl runs **synchronously** (blocks the HTTP request) — background tasks in Phase 3

### Step 4 — GET /pages and GET /pages/{id} ✅
- `api/routes/pages.py` queries the `pages` table
- Results serialized via `PageResponse` Pydantic schema (`from_attributes=True`)
- Pagination via `?skip=0&limit=20` query params

### Step 5 — GET /crawl/status ✅
- Returns stats from the last crawl's in-memory frontier snapshot
- Fields: `pages_crawled`, `pages_failed`, `queue_size`, `unique_urls_seen`, `domain_breakdown`

### Step 6 — Pydantic schemas ✅
- `CrawlRequest` — validates `seed_urls` (must be valid HTTP/HTTPS URLs) and `max_pages` (1–500)
- `CrawlResponse` — summary returned after crawl completes
- `PageResponse` — single page record (ORM-compatible via `from_attributes=True`)
- `StatusResponse` — crawl statistics

### Step 7 — Manual testing ✅
- FastAPI auto-docs at `/docs` (Swagger UI) — hit each endpoint interactively
- Verified DB rows appear after POST /crawl

---

## New Dependencies

```
fastapi           ← web framework
uvicorn           ← ASGI server
sqlalchemy        ← ORM + query builder
psycopg2-binary   ← PostgreSQL driver
pydantic          ← request/response validation (included with FastAPI)
```

Install:
```bash
pip install -r requirements.txt
```

---

## Design Decisions Made in Phase 2

| Decision | Rationale |
|---|---|
| **Synchronous crawl** | POST /crawl blocks until done. Intentional: understand crawl → DB pipeline before introducing Celery/Redis background tasks (Phase 3) |
| **Upsert on conflict** | `INSERT … ON CONFLICT DO UPDATE` makes crawling idempotent. Re-crawling a URL updates the row instead of raising a unique-constraint error |
| **`create_all()` on startup** | Zero-config for development. Alembic migrations replace this from Phase 3 onward |
| **Module-level frontier snapshot** | `_last_frontier` stores the last crawl's state for `/status`. Simple in-process state is sufficient for Phase 2; Redis replaces it in Phase 3 |
| **Phase 1 code untouched** | `fetcher.fetch`, `frontier.Frontier`, `parser.extract_links` are imported as-is. Phase 2 adds a new layer without modifying the existing one |
| **`from_attributes=True`** | Enables Pydantic to read directly from SQLAlchemy ORM row objects without manual conversion |

---

## Concepts Introduced in Phase 2

| Concept | Where |
|---|---|
| REST API design (routes, methods, status codes) | `api/routes/` |
| Request validation | Pydantic schemas (`CrawlRequest`) |
| Response serialization | Pydantic schemas (`PageResponse`, `StatusResponse`) |
| ORM (Object-Relational Mapping) | SQLAlchemy `Page` model |
| Database session management | `db/session.py` — `get_db()` dependency |
| SQL — INSERT, SELECT, WHERE, LIMIT, ON CONFLICT | `routes/crawl.py`, `routes/pages.py` |
| Pagination | `GET /pages?skip=&limit=` |
| Upsert / idempotent writes | `INSERT … ON CONFLICT DO UPDATE` |
| Separating concerns (routes / db / schemas) | Folder structure |
| Auto-generated API docs | FastAPI `/docs` (Swagger UI) |
| Lifespan context (startup/shutdown hooks) | `api/main.py` |

---

## What Phase 2 Does NOT Do

| Missing | Added in |
|---|---|
| Background crawl (non-blocking POST /crawl) | Phase 3 — Redis task queue |
| Multiple crawler workers | Phase 4 — distributed crawling |
| Retries + backoff | Phase 5 — reliability |
| Full-text search | Phase 6 — search engine |
| Docker / environment config | Phase 8 — DevOps |
| Auth / API keys | Phase 8 / production hardening |
| Database migrations (Alembic) | Phase 3 onward |
