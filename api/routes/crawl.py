"""
routes/crawl.py — Crawl Control Endpoints (Phase 2)

Routes:
    POST /api/v1/crawl          Start a crawl (runs synchronously in Phase 2).
    GET  /api/v1/crawl/status   Return stats from the last crawl run.

Phase 2 Design Decision — Synchronous crawl
────────────────────────────────────────────
The POST /crawl handler blocks until the crawl finishes.  This means the
HTTP client must wait (possibly minutes) for a response.  This is
intentional in Phase 2: we want to understand the crawl → DB pipeline
before introducing background task queues.

Phase 3 will move crawling into a background Celery/Redis task so the
POST returns immediately with a task ID, and the client polls GET /status.

How crawl results are persisted:
    After each successful fetch, a `pages` row is upserted via SQLAlchemy.
    Failed URLs are also recorded so we know what was attempted.
"""

import sys
import os
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Add the project root to sys.path so we can import the crawler package.
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from crawler.fetcher import fetch                # Phase 1 fetcher (unchanged)
from crawler.frontier import Frontier            # Phase 1 frontier (unchanged)
from crawler.parser import extract_links         # Phase 1 parser (unchanged)

from api.db.session import get_db
from api.db.models import Page
from api.schemas import CrawlRequest, CrawlResponse, StatusResponse

router = APIRouter(prefix="/api/v1", tags=["Crawl"])

# ── Module-level state for GET /status ───────────────────────────────────────
# In Phase 2 a single request runs synchronously, so we store the last
# run's frontier snapshot here.  Phase 3 will replace this with Redis.

_last_frontier: Frontier | None = None
_last_pages_crawled: int = 0
_last_pages_failed: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_title(html: str) -> str | None:
    """
    Pull the page title from raw HTML using a lightweight BeautifulSoup parse.

    Returns the stripped text of the first <title> tag, or None.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("title")
    if tag and tag.string:
        return tag.string.strip()
    return None


def _upsert_page(
    db: Session,
    *,
    url: str,
    title: str | None,
    http_status: int | None,
    crawl_status: str,
) -> None:
    """
    Insert a page row, or update it if the URL already exists.

    Uses PostgreSQL's INSERT … ON CONFLICT DO UPDATE so re-crawling a URL
    updates the existing row instead of raising a unique-constraint error.
    """
    stmt = (
        pg_insert(Page)
        .values(
            url=url,
            title=title,
            http_status=http_status,
            crawl_status=crawl_status,
        )
        .on_conflict_do_update(
            index_elements=["url"],
            set_={
                "title": title,
                "http_status": http_status,
                "crawl_status": crawl_status,
            },
        )
    )
    db.execute(stmt)


# ── POST /api/v1/crawl ────────────────────────────────────────────────────────

@router.post("/crawl", response_model=CrawlResponse, status_code=200)
def start_crawl(body: CrawlRequest, db: Session = Depends(get_db)) -> CrawlResponse:
    """
    Start a synchronous crawl.

    Accepts a list of seed URLs and a page limit.  Runs the Phase 1 crawl
    loop, writing every result to PostgreSQL, then returns a summary.

    **Phase 2 note**: this request blocks until the crawl finishes.
    Large page limits (e.g. 500) will cause long HTTP timeouts.
    Background crawling is introduced in Phase 3.

    Parameters
    ----------
    body : CrawlRequest
        ``{ "seed_urls": [...], "max_pages": N }``

    Returns
    -------
    CrawlResponse
        Summary of the completed crawl.
    """
    global _last_frontier, _last_pages_crawled, _last_pages_failed

    seed_urls: list[str] = [str(u) for u in body.seed_urls]
    max_pages: int = body.max_pages

    frontier = Frontier()
    for url in seed_urls:
        frontier.add(url)

    pages_crawled = 0
    pages_failed = 0

    while not frontier.is_empty():
        if pages_crawled >= max_pages:
            break

        url = frontier.next()
        if url is None:
            break

        # ── Fetch ─────────────────────────────────────────────────────────────
        html = fetch(url)

        if html is None:
            # Record the failure.
            pages_failed += 1
            _upsert_page(db, url=url, title=None, http_status=None, crawl_status="failed")
            db.commit()
            continue

        pages_crawled += 1
        frontier.mark_crawled(url)

        # ── Extract title ─────────────────────────────────────────────────────
        title = _extract_title(html)

        # ── Persist to PostgreSQL ─────────────────────────────────────────────
        _upsert_page(db, url=url, title=title, http_status=200, crawl_status="success")
        db.commit()

        # ── Discover new URLs ─────────────────────────────────────────────────
        links = extract_links(html, base_url=url)
        for link in links:
            frontier.add(link)

    # Save snapshot for GET /status.
    _last_frontier = frontier
    _last_pages_crawled = pages_crawled
    _last_pages_failed = pages_failed

    return CrawlResponse(
        message="Crawl completed",
        seed_count=len(seed_urls),
        max_pages=max_pages,
        pages_crawled=pages_crawled,
    )


# ── GET /api/v1/crawl/status ──────────────────────────────────────────────────

@router.get("/crawl/status", response_model=StatusResponse)
def crawl_status() -> StatusResponse:
    """
    Return statistics from the last crawl run.

    Reads the in-memory frontier snapshot saved by the most recent
    POST /crawl call.  Returns zeros if no crawl has run yet.

    Returns
    -------
    StatusResponse
        Counts and per-domain breakdown from the last crawl.
    """
    if _last_frontier is None:
        return StatusResponse(
            pages_crawled=0,
            pages_failed=0,
            queue_size=0,
            unique_urls_seen=0,
            domain_breakdown={},
        )

    return StatusResponse(
        pages_crawled=_last_pages_crawled,
        pages_failed=_last_pages_failed,
        queue_size=_last_frontier.queue_size(),
        unique_urls_seen=_last_frontier.seen_count(),
        domain_breakdown=_last_frontier.domain_stats(),
    )
