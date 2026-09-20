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
| 1 | Basic Crawler (seed → fetch → extract → queue) | ✅ In progress |
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
│   └── frontier.py        ← In-memory URL queue + deduplication
├── PHASE_1_CRAWLER.md     ← Phase 1 workflow & design notes
└── distributed_web_crawler_search_engine_project.md  ← Full project spec
```

---

## Documentation

- [`PHASE_1_CRAWLER.md`](./PHASE_1_CRAWLER.md) — Phase 1 data flow, code walkthrough, and concepts
- [`distributed_web_crawler_search_engine_project.md`](./distributed_web_crawler_search_engine_project.md) — Full project specification
