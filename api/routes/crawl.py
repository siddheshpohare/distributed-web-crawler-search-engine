"""
routes/crawl.py — Crawl Endpoints (Phase 2)

POST /api/v1/crawl          → Start a new crawl job
GET  /api/v1/crawl/status   → Get live crawl statistics from the DB
"""

from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from api.db.session import get_db
from api.db.models import Page
from api.schemas import CrawlRequest, CrawlResponse, StatusResponse

router = APIRouter(prefix="/api/v1", tags=["Crawl"])


# ── POST /api/v1/crawl ────────────────────────────────────────────────────────

@router.post("/crawl", response_model=CrawlResponse)
def start_crawl(payload: CrawlRequest, db: Session = Depends(get_db)):
    """
    Start a new crawl job.

    Receives seed URLs and max_pages, enqueues a background crawl task,
    and returns a summary acknowledgement.

    Parameters
    ----------
    payload : CrawlRequest
        JSON body containing ``seed_urls`` (list of HTTP/HTTPS URLs) and
        ``max_pages`` (int, 1–500, default 50).

    Returns
    -------
    CrawlResponse
        Confirmation message with seed count, max_pages, and pages_crawled
        (0 at submission time — crawl runs asynchronously).
    """
    # TODO: Replace with Celery task dispatch in Phase 3.
    # e.g. crawl_task.delay([str(u) for u in payload.seed_urls], payload.max_pages)
    return CrawlResponse(
        message="Crawl started",
        seed_count=len(payload.seed_urls),
        max_pages=payload.max_pages,
        pages_crawled=0,
    )


# ── GET /api/v1/crawl/status ──────────────────────────────────────────────────

@router.get("/crawl/status", response_model=StatusResponse)
def get_crawl_status(db: Session = Depends(get_db)):
    """
    Return live crawl statistics from the database.

    Queries the ``pages`` table to compute counts and a per-domain breakdown
    of crawled pages.

    Returns
    -------
    StatusResponse
        ``pages_crawled``, ``pages_failed``, ``queue_size``,
        ``unique_urls_seen``, and ``domain_breakdown`` (sorted descending).
    """
    pages_crawled = db.query(Page).filter(Page.crawl_status == "success").count()
    pages_failed  = db.query(Page).filter(Page.crawl_status == "failed").count()
    unique_urls_seen = db.query(Page).count()

    # Build domain breakdown from all URLs stored in the DB.
    rows = (
        db.query(Page.url, func.count(Page.id))
        .group_by(Page.url)
        .all()
    )
    domain_breakdown: dict[str, int] = {}
    for url, count in rows:
        domain = urlparse(url).netloc
        domain_breakdown[domain] = domain_breakdown.get(domain, 0) + count

    # Sort descending by page count.
    domain_breakdown = dict(
        sorted(domain_breakdown.items(), key=lambda x: -x[1])
    )

    return StatusResponse(
        pages_crawled=pages_crawled,
        pages_failed=pages_failed,
        queue_size=0,           # Update in Phase 3 when a live frontier/queue exists.
        unique_urls_seen=unique_urls_seen,
        domain_breakdown=domain_breakdown,
    )