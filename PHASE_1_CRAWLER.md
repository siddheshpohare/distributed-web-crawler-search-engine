# Phase 1 — Basic Crawler

## What Was Built

A single-process, synchronous web crawler that:

1. Starts from one or more seed URLs
2. Fetches each page over HTTP
3. Extracts all links from the HTML
4. Enqueues new (unseen) links using a **domain-priority queue**
5. Always crawls next from the **domain with the lowest virtual crawl count** (fair interleaving + starvation-safe)
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

## Our Journey — How Phase 1 Evolved

Phase 1 was not written once and finalised. It went through three distinct
iterations, each exposing a real systems-engineering problem and requiring a
principled fix. Here is the full history.

---

### Iteration 1 — Plain FIFO Queue

#### What we built

The simplest possible frontier: a single `deque`. All URLs from all
domains sit in one queue in insertion order.

```
frontier = deque()
frontier.append("https://core-stack.org")
frontier.append("https://www.india.gov.in")
```

#### The problem it caused

When `core-stack.org` returned 70 links and `india.gov.in` returned 63,
all 70 of core-stack's links were ahead of india's in the queue.
core-stack was crawled 17 times before india got its second turn.

```
Run output (FIFO):
  Pages crawled: 20 | Unique URLs: 296
  core-stack.org : 17 pages
  india.gov.in   :  1 page   ← heavily starved
```

**Root cause:** FIFO is insertion-order biased. Whichever seed returns
more links first dominates the queue.

#### The bug in fetcher.py found alongside this

`india.gov.in` was returning HTTP 403. Reason: the default `httpx`
User-Agent is `python-httpx/…`, which the server blocks. Changing to a
real Chrome User-Agent fixed it.

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ..."
}
```

---

### Iteration 2 — Domain-Priority Min-Heap (Crawl Count Key)

#### What we changed

Replaced the plain deque with a `heapq` keyed by **per-domain crawl
count**. Each domain gets its own FIFO deque internally. The min-heap
decides which domain to serve next — always the one with the fewest
pages crawled.

```
Internal state:
  _domain_queues  : dict[domain → deque[url]]   per-domain FIFO
  _domain_counts  : dict[domain → int]          pages crawled per domain
  _heap           : min-heap[(crawl_count, insertion_order, domain)]
  _in_heap        : set[str]                    dedup guard
  _seen           : set[url]                    global deduplication
  _insertion_order: dict[str, int]              stable tiebreaker
```

`mark_crawled(url)` increments the domain's count after every successful
fetch, sinking it in priority so the less-crawled domain rises to the top.

#### Results

```
Run output (domain-priority heap):
  Pages crawled: 20 | Unique URLs: 876   ← +580 URLs discovered

  DOMAIN STATS:
    pib.gov.in              2 page(s)
    www.earthengine.app     2 page(s)
    earthengine.google.com  2 page(s)
    core-stack.org          1 page(s)
    www.india.gov.in        1 page(s)
    ...17 domains total
```

17 domains each got 1–2 crawls. Unique URLs discovered nearly tripled
because the crawler explored more of the web graph by staying fair.

#### Priority selection — example trace

```
Heap after both seeds crawled once:
  (1, 0, "core-stack.org")   ← insertion order 0
  (1, 1, "india.gov.in")     ← insertion order 1

next() pops core-stack (lower insertion_order tiebreaker)
  → mark_crawled() → core-stack count = 2
  → re-push (2, 0, "core-stack.org")

Heap now:
  (1, 1, "india.gov.in")     ← count=1 → picked next!
  (2, 0, "core-stack.org")   ← sinks lower

Result: domains alternate, staying within ±1 of each other.
```

---

### Iteration 3 — Virtual-Time Floor (Dormant Flow Burst Fix)

#### The new problem discovered

After Iteration 2 was working correctly for concurrent active domains,
a deeper scheduling flaw was identified — the **Dormant Flow Burst**
problem (also called the Sleeping Process Problem in systems engineering).

This is the exact same class of starvation bug that forced both the
**Linux kernel CFS CPU scheduler** and **network packet routers** to
redesign their priority algorithms.

#### How the bug manifests

```
Step  1: Domain A added to frontier. count(A) = 0.
Step  2: Domain B added to frontier. count(B) = 0.
         B has no URLs yet — it immediately goes empty.
Steps 3–90: Only A has URLs. A crawls 88 pages. count(A) = 88.
             The heap floor (lowest active key) advances to 88.
Step 90: Someone discovers 50 links for Domain B.
         B re-enters the heap with count(B) = 0.
         0 << 88  →  B wins every heap pop.
         B crawls 88 consecutive times before A gets a single turn.
         Domain A is starved, even though it did nothing wrong.
```

The lifetime count is a **frozen historical debt** — B was absent,
not slow. It should not be punished with 88 free turns the moment it
comes back.

#### The analogy: Linux CFS

| Linux CFS | Our Frontier |
|---|---|
| `min_vruntime` — the virtual runtime of the current leftmost task in the red-black tree | `_global_min_count` — the virtual-time floor |
| When a sleeping task wakes up, its `vruntime` is clamped to `max(own_vruntime, min_vruntime)` | When a domain is pushed, its heap key is clamped to `max(own_count, _global_min_count)` |
| The waking task gets one scheduling slot, not hundreds of catch-up rounds | The reactivating domain lands at the floor, not at its stale historical count |

#### What we changed — three interlocking parts

**1. New field: `_global_min_count`** — the virtual-time floor

```python
self._global_min_count: int = 0
```

A monotonically increasing counter. It advances by 1 every time a URL
is served, acting as a global scheduling clock.

**2. Push-time clamp in `_push_domain`**

```python
# OLD (Iteration 2):
heapq.heappush(self._heap, (self._domain_counts[domain], order, domain))

# NEW (Iteration 3):
virtual_count = max(self._domain_counts[domain], self._global_min_count)
heapq.heappush(self._heap, (virtual_count, order, domain))
```

A domain that was dormant while others advanced is pushed at the
floor, not at its stale historical count. It gets **one** priority
slot, not 88.

**3. Pop-time tick + belt-and-suspenders clamp in `next()`**

```python
# Pop-time clamp — catches stale heap entries pushed before floor advanced
effective_count = max(raw_count, self._global_min_count)

# Advance the floor by one tick (one scheduling quantum consumed).
# Without this, a domain clamped to floor=N re-pushes at N every turn,
# beating active domains at N+2 indefinitely.
self._global_min_count = effective_count + 1
```

The `+1` tick is the critical piece. Without it:
- B bursts in, gets clamped to floor=86.
- B is served, re-pushed with `max(count=0, floor=86) = 86`.
- Floor doesn't advance (86 == 86).
- B wins the next pop again. And again. Infinite starvation loop.

The tick ensures each URL served consumes one virtual-time unit, so
B's re-push key becomes `max(0, 87) = 87` next turn, then `88`, then
it reaches parity with A and they interleave fairly.

#### Proof — test output

```
Scenario: A crawls 88 pages while B is absent. Then 50 B-URLs burst in.

WITHOUT fix  →  B gets 88 consecutive turns before A gets one.
WITH fix     →  B enters at virtual_count=88 (same as A).
                B gets 0 consecutive turns before A. They interleave immediately.

Test output:
  _global_min_count (floor) = 88
  B enters heap with virtual_count = 88   ✓ (was 0 without fix)

  Next 20 picks after B burst:
    domain-a.com: 2 turns
    domain-b.com: 18 turns
    (A's 2 remaining URLs run first by insertion-order, then B and A interleave)

  Consecutive B turns before A gets its first pick: 0   ✓
  PASS: Domain A was NOT starved.
```

---

## Data Flow (Current)

```
SEED_URLS (list in main.py)
        │
        ▼
┌──────────────────────┐
│       Frontier       │  ← Virtual-time domain-priority min-heap
│    (frontier.py)     │  ← Per-domain FIFO queues
│                      │  ← _global_min_count (floor clock)
│                      │  ← Seen-set for deduplication
└──────────┬───────────┘
           │  frontier.next()  ← picks domain with lowest virtual count
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
│                      │  ← frontier.mark_crawled(url) increments count
└──────────┬───────────┘
           │
           ▼
       (loop back)
```

---

## File-by-File Explanation

### `frontier.py` — Domain-Priority URL Frontier

**Purpose:** Keeps track of what to crawl next, ensuring fair interleaving
across multiple seed domains with protection against dormant-domain starvation.

**Internal state:**

| Variable | Type | Role |
|---|---|---|
| `_domain_queues` | `dict[str, deque[str]]` | Per-domain FIFO queue of pending URLs |
| `_domain_counts` | `dict[str, int]` | Pages successfully crawled per domain |
| `_heap` | `list[tuple]` | Min-heap of `(virtual_count, insertion_order, domain)` |
| `_in_heap` | `set[str]` | Domains currently on the heap (avoids duplicates) |
| `_seen` | `set[str]` | Every URL ever added (global deduplication) |
| `_insertion_order` | `dict[str, int]` | Stable tiebreaker for equal-count domains |
| `_global_min_count` | `int` | Virtual-time floor — advances +1 per URL served |

**Key methods:**

| Method | What it does |
|---|---|
| `add(url)` | Adds URL to domain's deque if not in `_seen`. Pushes domain onto heap with clamped virtual count. |
| `next()` | Pops lowest virtual-count domain. Clamps stale heap entries to floor. Advances floor by +1. Returns next URL. Re-pushes domain with fresh clamped key. |
| `mark_crawled(url)` | Increments real crawl count for the URL's domain. Called after every successful fetch. |
| `is_empty()` | Returns `True` when no domains have pending URLs. |
| `seen_count()` | Total unique URLs encountered. |
| `queue_size()` | Total pending URLs across all domains. |
| `domain_stats()` | Returns a `dict[domain → count]` sorted by count descending. |

**Why a min-heap on virtual count (not raw count)?**

The heap key is `max(own_count, _global_min_count)` — not just `own_count`.
This is the virtual-time clamping mechanism. See Iteration 3 above for the
full explanation of why raw count causes the Dormant Flow Burst.

**Phase 3 change:** This module will be replaced by a Redis-backed queue
so multiple crawler workers can share the frontier atomically.

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

    url  = frontier.next()            # Step 0: dequeue (lowest virtual-count domain)

    html = fetch(url)                 # Step 1: HTTP GET
    if html is None:
        print [SKIP]
        continue                      # skip on failure (no count increment)

    pages_crawled += 1
    frontier.mark_crawled(url)        # Step 1b: increment domain's real count

    links = extract_links(html, url)  # Step 2: parse HTML

    for link in links:                # Step 3: enqueue new URLs
        frontier.add(link)

print summary + domain stats
```

---

## Bugs Fixed During Phase 1

| Bug | Symptom | Iteration | Fix |
|---|---|---|---|
| Bot User-Agent | `india.gov.in` returned HTTP 403 | 1 | Changed to Chrome browser User-Agent |
| FIFO starvation | Second seed domain barely crawled | 1→2 | Replaced deque with domain-priority min-heap |
| Counter display | `(2)` printed twice after a skip | 1 | Moved `[CRAWL] (n)` print to after successful fetch |
| Dormant Flow Burst | Reactivated domain monopolised crawler for dozens of turns | 2→3 | Added `_global_min_count` virtual-time floor with push-time clamp + pop-time tick |

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
| Dormant Flow Burst / Sleeping Process Problem | `frontier.py` — `_global_min_count` virtual clock |
| Virtual-time scheduling (CFS analogy) | `frontier.py` — push-time clamp + pop-time tick |
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
