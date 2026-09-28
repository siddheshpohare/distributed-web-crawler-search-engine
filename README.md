# Distributed Web Crawler & Search Engine

A production-style backend and distributed-systems project that crawls web pages, discovers new URLs, indexes content, and serves a search API.

Built in phases — from a simple single-process crawler to a fully distributed, observable, cloud-deployed system.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python |
| API Framework | FastAPI |
| Database | PostgreSQL |
| Cache / Queue | Redis |
| HTTP Client | httpx |
| HTML Parsing | BeautifulSoup |
| Search | Custom Inverted Index → OpenSearch |
| Ranking | TF-IDF → BM25 |
| Containerization | Docker + Docker Compose |
| CI/CD | GitHub Actions |
| Cloud | AWS |
| Monitoring | Prometheus + Grafana |
| Testing | pytest + Locust |

---

## Project Phases

| Phase | Focus | Status |
|---|---|---|
| 1 | Basic Crawler (seed → fetch → extract → queue) | ✅ Complete |
| 2 | REST API (FastAPI + PostgreSQL) | ✅ Complete |
| 3 | Redis Queue (async producer/consumer) | 🔜 |
| 4 | Distributed Crawling (multiple workers) | 🔜 |
| 5 | Reliability (retries, backoff, leases) | 🔜 |
| 6 | Search Engine (inverted index, BM25) | 🔜 |
| 7 | Performance (caching, indexes, pooling) | 🔜 |
| 8 | DevOps (Docker, CI/CD) | 🔜 |
| 9 | Observability (Prometheus, Grafana) | 🔜 |
| 10 | Cloud Deployment (AWS) | 🔜 |

---

## Phase 1 — Journey Summary

Phase 1 was built and refined through three distinct iterations. Each one
exposed a real systems-engineering problem.

### Iteration 1 — Plain FIFO Queue
Started with a single `deque`. All URLs from all domains sit in one queue
in insertion order. The crawler worked but heavily starved the second seed
domain (17 core-stack pages vs 1 india.gov.in page in 20 crawls).

Also discovered and fixed: `india.gov.in` blocking the default `httpx`
User-Agent with HTTP 403 — fixed by using a Chrome browser User-Agent.

### Iteration 2 — Domain-Priority Min-Heap
Replaced the plain deque with a `heapq` keyed by **per-domain crawl count**.
Each domain gets its own internal FIFO deque. The heap always serves the
domain with the fewest pages crawled — fair round-robin across all active
domains.

Result: 17 domains each got 1–2 crawls instead of one domain dominating.
Unique URLs discovered jumped from 296 → 876.

### Iteration 3 — Virtual-Time Floor (Dormant Flow Burst Fix)
Identified the **Dormant Flow Burst** problem — the same class of starvation
bug that forced the Linux kernel CFS scheduler to adopt virtual runtimes.

**The bug:** A domain that was dormant (had no URLs) while others advanced
re-enters the heap with its stale historical count (e.g. 0 while the active
domain is at 88). It gets 88 consecutive turns, starving the active domain
that did nothing wrong.

**The fix:** Added `_global_min_count` — a virtual-time floor that advances
by +1 on every URL served. When any domain is pushed onto the heap, its key
is clamped to `max(own_count, floor)`. A dormant domain that reactivates
lands at the current floor (one priority slot) rather than its stale low
count.

This is identical in principle to how Linux CFS clamps a waking task's
`vruntime` to `min_vruntime` before reinserting it into the scheduler's
red-black tree.

---

## Phase 2 — Journey Summary

Phase 2 wraps the Phase 1 crawler behind a REST API using **FastAPI** and
introduces the first **persistent storage** — PostgreSQL.

### What changed

| Before (Phase 1) | After (Phase 2) |
|---|---|
| `python main.py` (script) | `uvicorn api.main:app` (always-on server) |
| `print()` output | PostgreSQL rows via SQLAlchemy |
| Hardcoded `SEED_URLS` | `POST /api/v1/crawl` (trigger via HTTP) |
| No query capability | `GET /api/v1/pages`, `GET /api/v1/pages/{id}` |
| No status visibility | `GET /api/v1/crawl/status` |

### Key design decisions

| Decision | Why |
|---|---|
| Synchronous crawl in Phase 2 | Understand the crawl → DB pipeline before introducing task queues |
| PostgreSQL upsert (`ON CONFLICT DO UPDATE`) | Re-crawling a URL updates the row instead of raising a constraint error |
| `Base.metadata.create_all()` on startup | No manual SQL needed for dev; Alembic replaces this in Phase 3 |
| `from_attributes=True` on Pydantic schemas | Allows Pydantic to read directly from SQLAlchemy ORM rows |
| Phase 1 crawler untouched | `fetcher`, `frontier`, `parser` imported as-is — zero coupling |
| Module-level frontier snapshot for `/status` | Simple in-memory state for Phase 2; Redis replaces it in Phase 3 |

---

## Quick Start

### Phase 1 — Run the crawler directly

```bash
pip install httpx beautifulsoup4

cd crawler
python main.py
```

### Phase 2 — Run the REST API

```bash
# 1. Install all dependencies
pip install -r requirements.txt

# 2. Create the PostgreSQL database (PostgreSQL must be running)
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

#### Trigger a crawl via API

```bash
curl -X POST http://127.0.0.1:8000/api/v1/crawl \
  -H "Content-Type: application/json" \
  -d '{"seed_urls": ["https://example.com"], "max_pages": 10}'
```

---

## Project Structure

```
.
├── api/                        ← Phase 2: REST API
│   ├── main.py                 ← FastAPI app, mounts all routers
│   ├── schemas.py              ← Pydantic request/response models
│   ├── db/
│   │   ├── session.py          ← SQLAlchemy engine + session factory
│   │   └── models.py           ← ORM models (Page table)
│   └── routes/
│       ├── health.py           ← GET /health
│       ├── crawl.py            ← POST /api/v1/crawl, GET /api/v1/crawl/status
│       └── pages.py            ← GET /api/v1/pages, GET /api/v1/pages/{id}
├── crawler/                    ← Phase 1: basic crawl loop (unchanged)
│   ├── main.py                 ← Entry point & crawl loop
│   ├── fetcher.py              ← HTTP GET via httpx
│   ├── parser.py               ← Link extraction via BeautifulSoup
│   └── frontier.py             ← Virtual-time domain-priority URL frontier
├── requirements.txt            ← All Phase 1 + Phase 2 dependencies
├── setup_db.sql                ← Manual SQL for DB/table setup
├── PHASE_1_CRAWLER.md          ← Phase 1 journey, design notes & code walkthrough
├── PHASE_2_API.md              ← Phase 2 spec: endpoints, schema, build plan
└── distributed_web_crawler_search_engine_project.md  ← Full project spec
```

---

## API Endpoints (Phase 2)

| Method | Endpoint | What it does |
|---|---|---|
| `GET` | `/health` | Liveness check — returns `{"status": "ok"}` |
| `POST` | `/api/v1/crawl` | Start a crawl with seed URLs + page limit |
| `GET` | `/api/v1/crawl/status` | Return stats from the last crawl run |
| `GET` | `/api/v1/pages` | List all crawled pages (paginated) |
| `GET` | `/api/v1/pages/{id}` | Get a single page record by ID |

Interactive docs: **http://127.0.0.1:8000/docs**

---

## Key Engineering Decisions

### Phase 1

| Decision | Why |
|---|---|
| `heapq` over `deque` | FIFO causes domain starvation when seeds have unequal link counts |
| Per-domain internal deques | BFS within a domain; heap decides cross-domain ordering |
| Virtual-time floor (`_global_min_count`) | Prevents Dormant Flow Burst — dormant domains cannot monopolise the scheduler when they reactivate |
| Push-time clamp + pop-time tick | Two-sided guard: heap entries are always ordered by virtual time, and the floor ticks forward on every crawl |
| Chrome User-Agent | Some servers block bot User-Agents with HTTP 403 |
| `follow_redirects=True` | Handles HTTP 301/302 transparently |
| Skip on fetch failure (no count increment) | Failed pages don't waste the domain's priority budget |

### Phase 2

| Decision | Why |
|---|---|
| Synchronous `POST /crawl` | Simplest path to understand crawl → DB pipeline before async task queues |
| Upsert (`ON CONFLICT DO UPDATE`) | Idempotent writes — re-crawling a URL never raises a DB error |
| `create_all()` on lifespan startup | Zero-config dev setup; migrations (Alembic) come in Phase 3 |
| Module-level `_last_frontier` for `/status` | Simple in-process state for Phase 2; Redis replaces it in Phase 3 |

---

## Documentation

- [`PHASE_1_CRAWLER.md`](./PHASE_1_CRAWLER.md) — Full Phase 1 journey: three iterations, bugs found, fixes applied, concepts covered
- [`PHASE_2_API.md`](./PHASE_2_API.md) — Phase 2 build record: what was built, design decisions, how to run
- [`distributed_web_crawler_search_engine_project.md`](./distributed_web_crawler_search_engine_project.md) — Full project specification
