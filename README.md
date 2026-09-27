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
| 2 | REST API (FastAPI) | 🔜 |
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

## Quick Start (Phase 1)

```bash
# Install dependencies
pip install httpx beautifulsoup4

# Run the crawler
cd crawler
python main.py
```

---

## Project Structure

```
.
├── crawler/               ← Phase 1: basic crawl loop
│   ├── main.py            ← Entry point & crawl loop
│   ├── fetcher.py         ← HTTP GET via httpx
│   ├── parser.py          ← Link extraction via BeautifulSoup
│   └── frontier.py        ← Virtual-time domain-priority URL frontier
├── PHASE_1_CRAWLER.md     ← Full Phase 1 journey, design notes & code walkthrough
└── distributed_web_crawler_search_engine_project.md  ← Full project spec
```

---

## Key Engineering Decisions in Phase 1

| Decision | Why |
|---|---|
| `heapq` over `deque` | FIFO causes domain starvation when seeds have unequal link counts |
| Per-domain internal deques | BFS within a domain; heap decides cross-domain ordering |
| Virtual-time floor (`_global_min_count`) | Prevents Dormant Flow Burst — dormant domains cannot monopolise the scheduler when they reactivate |
| Push-time clamp + pop-time tick | Two-sided guard: heap entries are always ordered by virtual time, and the floor ticks forward on every crawl so re-pushed domains don't freeze at a stale position |
| Chrome User-Agent | Some servers block bot User-Agents with HTTP 403 |
| `follow_redirects=True` | Handles HTTP 301/302 transparently |
| Skip on fetch failure (no count increment) | Failed pages don't waste the domain's priority budget |

---

## Documentation

- [`PHASE_1_CRAWLER.md`](./PHASE_1_CRAWLER.md) — Full Phase 1 journey: three iterations, bugs found, fixes applied, concepts covered
- [`PHASE_2_API.md`](./PHASE_2_API.md) — Phase 2 plan: FastAPI + PostgreSQL, endpoints, DB schema, step-by-step build order
- [`distributed_web_crawler_search_engine_project.md`](./distributed_web_crawler_search_engine_project.md) — Full project specification
