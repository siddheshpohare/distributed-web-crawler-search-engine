# Phase 2 — REST API (FastAPI)

## Goal

Expose the crawler as a web service. Instead of running `python main.py`
directly, Phase 2 wraps the crawler behind a REST API so it can be
triggered, monitored, and queried over HTTP.

This also introduces the first **persistent storage** — PostgreSQL to
store every crawled page as a durable record instead of printing to stdout.

---

## What We Are Adding

```
Phase 1                          Phase 2
──────────────────────────       ──────────────────────────────────────
python main.py (script)    →     FastAPI server (always-on)
print() output             →     PostgreSQL (durable records)
hardcoded SEED_URLS        →     POST /crawl  (trigger via API)
no query capability        →     GET  /search, GET /pages
```

---

## New Folder Structure

```
.
├── api/
│   ├── main.py          ← FastAPI app, mounts all routers
│   ├── routes/
│   │   ├── crawl.py     ← POST /crawl, GET /crawl/status
│   │   ├── pages.py     ← GET /pages, GET /pages/{id}
│   │   └── health.py    ← GET /health
│   ├── db/
│   │   ├── session.py   ← SQLAlchemy engine + session factory
│   │   └── models.py    ← ORM models (Page table)
│   └── schemas.py       ← Pydantic request/response models
├── crawler/             ← Phase 1 code (unchanged)
│   ├── main.py
│   ├── fetcher.py
│   ├── parser.py
│   └── frontier.py
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
{ "message": "Crawl started", "seed_count": 1, "max_pages": 50 }
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
    "crawled_at": "2026-09-27T09:00:00Z"
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

Every successful fetch writes one row. Failed/skipped URLs are also
recorded (so we know what was attempted).

---

## Step-by-Step Build Plan

### Step 1 — Set up FastAPI skeleton
- `pip install fastapi uvicorn`
- Create `api/main.py` with a bare FastAPI app
- Add `/health` endpoint
- Confirm `uvicorn api.main:app --reload` works

### Step 2 — Connect PostgreSQL
- `pip install sqlalchemy psycopg2-binary`
- Create `api/db/session.py` — engine + `SessionLocal`
- Create `api/db/models.py` — `Page` ORM model
- Run `CREATE TABLE pages …` (manual SQL for now, migrations in Phase 3)
- Confirm a test insert/select works

### Step 3 — Wire crawler into a POST /crawl route
- Move the Phase 1 crawl loop into a callable function
- After each successful fetch, write a row to `pages` via SQLAlchemy
- Call that function from the `POST /crawl` handler
- For now, run the crawl **synchronously** (blocks the request) — async
  background tasks come in Phase 3

### Step 4 — Build GET /pages and GET /pages/{id}
- Query the `pages` table
- Return results as JSON using Pydantic schemas
- Add simple pagination (`?skip=0&limit=20`)

### Step 5 — Build GET /crawl/status
- Return live stats: pages crawled, queue size, domain breakdown
- Read from the frontier object (in-memory for now)

### Step 6 — Pydantic schemas
- `CrawlRequest` — validates `seed_urls` and `max_pages`
- `PageResponse` — shapes what the API returns for a page
- `StatusResponse` — shapes the crawl status response

### Step 7 — Test everything manually
- Use the FastAPI auto-docs at `/docs` (Swagger UI)
- Hit each endpoint, verify DB rows appear

---

## New Dependencies

```
fastapi          ← web framework
uvicorn          ← ASGI server
sqlalchemy       ← ORM + query builder
psycopg2-binary  ← PostgreSQL driver
pydantic         ← request/response validation (included with FastAPI)
```

Install:
```bash
pip install fastapi uvicorn sqlalchemy psycopg2-binary
```

---

## Concepts Introduced in Phase 2

| Concept | Where |
|---|---|
| REST API design (routes, methods, status codes) | `api/routes/` |
| Request validation | Pydantic schemas |
| Response serialization | Pydantic schemas |
| ORM (Object-Relational Mapping) | SQLAlchemy models |
| Database session management | `db/session.py` |
| SQL — INSERT, SELECT, WHERE, LIMIT | `routes/pages.py` |
| Pagination | `GET /pages?skip=&limit=` |
| Separating concerns (routes / db / schemas) | Folder structure |
| Auto-generated API docs | FastAPI `/docs` |

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
