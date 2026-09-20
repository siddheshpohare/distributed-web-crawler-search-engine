# Phase 1 — Basic Crawler

## What Was Built

A single-process, synchronous web crawler that:

1. Starts from one or more seed URLs
2. Fetches each page over HTTP
3. Extracts all links from the HTML
4. Enqueues new (unseen) links using a **domain-priority queue**
5. Always crawls next from the **least-crawled domain** (fair interleaving)
6. Repeats until the queue is empty or a page limit is reached

No database, no Redis, no async — just the core crawl loop to make the
basic mechanism clear before adding complexity.

---

## Folder Structure

```
crawler/
├── main.py       ← Entry point. Runs the crawl loop.
├── fetcher.py    ← Makes HTTP GET requests, returns HTML.
├── parser.py     ← Parses HTML, extracts & normalizes links.
└── frontier.py   ← Domain-priority URL queue + deduplication.
```

---

## Data Flow

```
SEED_URLS (list in main.py)
        │
        ▼
┌──────────────────────┐
│       Frontier       │  ← Domain-priority min-heap
│    (frontier.py)     │  ← Per-domain FIFO queues
│                      │  ← Seen-set for deduplication
└──────────┬───────────┘
           │  frontier.next()  ← picks least-crawled domain
           ▼
┌───────────────┐
│    Fetcher    │  ← httpx.get(url, timeout=10s)
│  (fetcher.py) │  ← Returns HTML string, or None on failure
└──────┬────────┘
       │  raw HTML
       ▼
┌───────────────┐
│    Parser     │  ← BeautifulSoup finds all <a href> tags
│  (parser.py)  │  ← Resolves relative URLs → absolute
│               │  ← Strips #fragments
│               │  ← Drops non-HTTP(S) links
└──────┬────────┘
       │  list of clean absolute URLs
       ▼
┌──────────────────────┐
│       Frontier       │  ← frontier.add(url) for each link
│    (frontier.py)     │  ← Only added if not in seen-set
│                      │  ← frontier.mark_crawled(url) sinks
│                      │     this domain's priority
└──────────┬───────────┘
           │
           ▼
       (loop back)
```

---

## File-by-File Explanation

### `frontier.py` — Domain-Priority URL Frontier

**Purpose:** Keeps track of what to crawl next, ensuring fair
interleaving across multiple seed domains.

**Internal state:**

| Variable | Type | Role |
|---|---|---|
| `_domain_queues` | `dict[str, deque[str]]` | Per-domain FIFO queue of pending URLs |
| `_domain_counts` | `dict[str, int]` | Pages successfully crawled per domain |
| `_heap` | `list[tuple]` | Min-heap of `(crawl_count, insertion_order, domain)` |
| `_in_heap` | `set[str]` | Domains currently on the heap (avoids duplicates) |
| `_seen` | `set[str]` | Every URL ever added (global deduplication) |
| `_insertion_order` | `dict[str, int]` | Stable tiebreaker for equal-count domains |

**Key methods:**

| Method | What it does |
|---|---|
| `add(url)` | Adds URL to its domain's deque if not in `_seen`. Pushes the domain onto the heap. |
| `next()` | Pops the domain with the lowest crawl count. Returns the next URL from that domain's deque. Re-pushes the domain if it has more URLs. |
| `mark_crawled(url)` | Increments the crawl count for the URL's domain. Call this after every successful fetch. |
| `is_empty()` | Returns `True` when no domains have pending URLs. |
| `seen_count()` | Total unique URLs encountered. |
| `queue_size()` | Total pending URLs across all domains. |
| `domain_stats()` | Returns a `dict[domain → count]` sorted by count descending. |

**Why a min-heap on crawl count?**

Without priority, a FIFO queue processes URLs in insertion order.
When seed A returns 70 links and seed B returns 60, all 70 of A's
links sit ahead of B's in the queue. A gets crawled 17 times before
B gets its second turn.

With the domain-priority heap, after crawling A once (count=1) and
B once (count=1), A's links are added with count=1 and B's with count=1.
The heap alternates between them. After each crawl, `mark_crawled()`
increments the count, pushing that domain down in priority so the
other domain rises to the top.

**Priority selection flow:**

```
Heap state after both seeds crawled:
  (1, 0, "core-stack.org")     ← insertion order 0
  (1, 1, "india.gov.in")       ← insertion order 1

next() pops core-stack (lower insertion order tiebreaker)
  → mark_crawled() → core-stack count = 2
  → re-push (2, 0, "core-stack.org")

Heap now:
  (1, 1, "india.gov.in")       ← count=1 → picked next!
  (2, 0, "core-stack.org")     ← sinks lower

Result: domains alternate, staying within ±1 of each other
```

**Why per-domain deques?**
FIFO within each domain — so pages within the same site are crawled
in the order they were discovered, which is natural BFS within a domain.

**Phase 3 change:** This module will be replaced by a Redis-backed
queue so multiple crawler workers can share the frontier atomically.

---

### `fetcher.py` — HTTP Fetcher

**Purpose:** Makes a single HTTP GET request and returns the HTML body.

**Library:** `httpx` (sync client)

**What it does:**

```
httpx.get(url, timeout=10s, follow_redirects=True)
    │
    ├─ HTTP 200 → return response.text (HTML string)
    │
    ├─ HTTP 4xx/5xx → print error, return None
    │
    ├─ Timeout → print error, return None
    │
    └─ Network error (DNS, reset) → print error, return None
```

**User-Agent sent:**
```
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36
```

> **Why not a bot User-Agent?**
> Servers like `india.gov.in` return HTTP 403 when they see a
> bot identifier. Using a real browser User-Agent avoids this block.
> In production, crawlers should respect `robots.txt` and identify
> themselves honestly — this is an educational tradeoff for Phase 1.

**Why `follow_redirects=True`?**
Many URLs redirect (HTTP 301/302). Without this, `http://example.com`
would fail instead of following to `https://example.com`.

**Phase 5 change:** This module will gain retries with exponential
backoff, per-domain rate limiting, and configurable timeout.

---

### `parser.py` — HTML Link Extractor

**Purpose:** Given raw HTML and the URL it came from, returns a clean
list of absolute URLs.

**Library:** `BeautifulSoup` (`html.parser` backend)

**Steps per link found in `<a href="...">` tags:**

```
Raw href value  (e.g.  "../catalogue/book.html")
        │
        ▼
urljoin(base_url, href)       ← Resolve relative → absolute
        │
        ▼
urlparse(absolute_url)        ← Break into components
        │
        ├─ scheme not in {http, https}?  → discard
        │   (drops mailto:, javascript:, ftp:, data:, etc.)
        │
        ├─ strip fragment (#section)     → same document, skip
        │
        └─ urlunparse(...)               → clean string
```

**URL normalization examples:**

| Raw href | Base URL | Result |
|---|---|---|
| `../about` | `http://example.com/blog/post` | `http://example.com/about` |
| `#top` | `http://example.com/page` | discarded (same page) |
| `mailto:x@y.com` | anything | discarded |
| `//cdn.example.com/img` | `http://example.com` | `http://cdn.example.com/img` |
| `/catalogue/book.html` | `http://books.toscrape.com/` | `http://books.toscrape.com/catalogue/book.html` |

**Phase 6 change:** This module will also extract `<title>`, headings,
and body text for the inverted index.

---

### `main.py` — Crawl Loop

**Purpose:** Wires everything together and runs the crawl.

**Configuration (top of file):**
```python
SEED_URLS = ["https://core-stack.org", "https://www.india.gov.in"]
MAX_PAGES  = 20          # None = crawl until frontier is empty
```

**Loop logic (pseudocode):**
```
seed Frontier with SEED_URLS

while frontier not empty AND pages_crawled < MAX_PAGES:

    url  = frontier.next()            # Step 0: dequeue (least-crawled domain)

    html = fetch(url)                 # Step 1: HTTP GET
    if html is None:
        print [SKIP]
        continue                      # skip on failure (no count increment)

    pages_crawled += 1
    frontier.mark_crawled(url)        # Step 1b: sink this domain in priority

    links = extract_links(html, url)  # Step 2: parse HTML

    for link in links:                # Step 3: enqueue new URLs
        frontier.add(link)

print summary + domain stats
```

---

## Actual Run Output

### Run 1 — FIFO queue (old behaviour)

```
Seed: core-stack.org, india.gov.in

[CRAWL] (1)  core-stack.org        ← 70 links
[CRAWL] (2)  india.gov.in          ← 63 links (403 before User-Agent fix)
[CRAWL] (3)  core-stack.org/       ← core-stack dominates from here
[CRAWL] (4)  core-stack.org/our-team-2/
...
[CRAWL] (20) core-stack.org/category/knowledge/nuts-bolts/

Pages crawled: 20 | Unique URLs: 296
core-stack.org: 17 pages | india.gov.in: 1 page   ← heavily skewed
```

### Run 2 — Domain-priority queue (current behaviour)

```
Seed: core-stack.org, india.gov.in

[CRAWL] (1)  core-stack.org           ← core-stack count = 1
[CRAWL] (2)  india.gov.in             ← india count = 1 (tied → india next)
[CRAWL] (3)  core-stack.org/          ← core-stack count = 2
[CRAWL] (4)  pib.gov.in               ← new domain (count 0 → highest prio)
[CRAWL] (5)  earthengine.google.com   ← new domain (count 0)
...alternating across 17 domains...

Pages crawled: 20 | Unique URLs: 876

DOMAIN STATS:
  pib.gov.in                   2 page(s)
  www.earthengine.app          2 page(s)
  earthengine.google.com       2 page(s)
  core-stack.org               1 page(s)
  www.india.gov.in             1 page(s)
  explorer.core-stack.org      1 page(s)
  ...17 domains total
```

**Key improvement:** 17 domains each got 1–2 crawls instead of
one domain dominating. Unique URLs discovered jumped from 296 → 876
because the crawler explored more of the web graph.

---

## Bugs Fixed in Phase 1

| Bug | Symptom | Fix |
|---|---|---|
| Bot User-Agent | `india.gov.in` returned HTTP 403 | Changed to Chrome browser User-Agent |
| FIFO starvation | Second seed domain barely crawled | Replaced deque with domain-priority min-heap |
| Counter display | `(2)` printed twice after a skip | Moved `[CRAWL] (n)` print to after successful fetch |

---

## Concepts Covered in Phase 1

| Concept | Where it appears |
|---|---|
| HTTP request/response | `fetcher.py` |
| HTTP status codes & error types | `fetcher.py` exception handling |
| Redirect following | `httpx follow_redirects=True` |
| HTML parsing | `parser.py` — BeautifulSoup |
| URL structure (scheme, host, path, fragment) | `parser.py` — `urlparse` |
| Relative URL resolution | `parser.py` — `urljoin` |
| URL normalization | `parser.py` — `_normalize()` |
| Deduplication with a set | `frontier.py` — `_seen` |
| Priority queue with heapq | `frontier.py` — `_heap` |
| Per-domain fairness | `frontier.py` — `_domain_counts` + `mark_crawled()` |
| FIFO starvation problem | Motivation for replacing deque with heap |
| Stable tiebreaker (insertion order) | `frontier.py` — `_insertion_order` |
| Basic fault tolerance (skip on failure) | `main.py` — `if html is None: continue` |

---

## Dependencies

```
httpx            ← HTTP client (sync)
beautifulsoup4   ← HTML parser
```

Install:
```bash
pip install httpx beautifulsoup4
```

Run:
```bash
cd crawler
python main.py
```

---

## What Phase 1 Does NOT Do

These limitations are intentional — each will be addressed in a later phase:

| Missing | Added in |
|---|---|
| Store crawled pages anywhere | Phase 1 (next step) — PostgreSQL |
| REST API to trigger/query crawls | Phase 2 — FastAPI |
| Shared queue across workers | Phase 3 — Redis |
| Multiple parallel workers | Phase 4 — distributed crawling |
| Retries + exponential backoff | Phase 5 — reliability |
| Per-domain rate limiting | Phase 5 — reliability |
| Robots.txt compliance | Phase 5 — reliability |
| Text extraction for search | Phase 6 — search engine |
| Inverted index + ranking | Phase 6 — search engine |
| Docker / CI/CD | Phase 8 — DevOps |
| Prometheus / Grafana | Phase 9 — observability |
| AWS deployment | Phase 10 — cloud |

---

## Next Step

Add PostgreSQL to Phase 1 to persist crawled page metadata:

```
pages table
───────────
id             SERIAL PRIMARY KEY
url            TEXT UNIQUE NOT NULL
title          TEXT
http_status    INTEGER
crawl_status   TEXT          ← success / failed / skipped
crawled_at     TIMESTAMPTZ
```

This turns the crawler from a script that prints output into a system
that builds a durable record of what it has seen.
