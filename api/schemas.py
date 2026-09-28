"""
schemas.py — Pydantic Request / Response Models (Phase 2)

Pydantic schemas validate incoming request bodies and shape outgoing
JSON responses.  They are separate from SQLAlchemy ORM models so that
the database representation and the API contract can evolve independently.

Schemas defined here:

    CrawlRequest    → body of POST /api/v1/crawl
    CrawlResponse   → response of POST /api/v1/crawl
    StatusResponse  → response of GET  /api/v1/crawl/status
    PageResponse    → response of GET  /api/v1/pages and GET /api/v1/pages/{id}
"""

from datetime import datetime

from pydantic import BaseModel, HttpUrl, Field, field_validator


# ── POST /api/v1/crawl ────────────────────────────────────────────────────────

class CrawlRequest(BaseModel):
    """
    Request body for starting a crawl.

    Attributes
    ----------
    seed_urls : list[str]
        One or more seed URLs to start crawling from.
        Must be valid HTTP/HTTPS URLs.
    max_pages : int
        Maximum number of pages to crawl.  Must be between 1 and 500.
        Defaults to 50.
    """

    seed_urls: list[HttpUrl] = Field(
        ...,
        min_length=1,
        description="One or more seed URLs (HTTP/HTTPS).",
        examples=[["https://example.com"]],
    )
    max_pages: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of pages to crawl (1–500).",
    )

    @field_validator("seed_urls")
    @classmethod
    def at_least_one_url(cls, v: list) -> list:
        if not v:
            raise ValueError("seed_urls must contain at least one URL.")
        return v


class CrawlResponse(BaseModel):
    """Response body returned after POST /api/v1/crawl completes."""

    message: str
    seed_count: int
    max_pages: int
    pages_crawled: int


# ── GET /api/v1/crawl/status ──────────────────────────────────────────────────

class StatusResponse(BaseModel):
    """
    Live crawl statistics.

    Attributes
    ----------
    pages_crawled : int
        Number of pages successfully crawled in the current/last run.
    pages_failed : int
        Number of URLs that failed to fetch.
    queue_size : int
        URLs currently waiting in the frontier.
    unique_urls_seen : int
        Total unique URLs ever added to the frontier.
    domain_breakdown : dict[str, int]
        Pages crawled per domain, sorted descending by count.
    """

    pages_crawled: int
    pages_failed: int
    queue_size: int
    unique_urls_seen: int
    domain_breakdown: dict[str, int]


# ── GET /api/v1/pages and GET /api/v1/pages/{id} ─────────────────────────────

class PageResponse(BaseModel):
    """
    A single crawled page record returned by the API.

    Attributes
    ----------
    id : int
        Database row ID.
    url : str
        The crawled URL.
    title : str | None
        Page title, if extracted.
    http_status : int | None
        HTTP response status code.
    crawl_status : str | None
        'success', 'failed', or 'skipped'.
    crawled_at : datetime
        UTC timestamp of when this page was crawled.
    """

    id: int
    url: str
    title: str | None
    http_status: int | None
    crawl_status: str | None
    crawled_at: datetime

    model_config = {"from_attributes": True}   # Enables ORM mode (SQLAlchemy → Pydantic).
