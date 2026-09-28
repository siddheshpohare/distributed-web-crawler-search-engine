"""
db/models.py — ORM Models (Phase 2)

Defines the SQLAlchemy ORM model for the `pages` table.

Schema:
    pages
    ─────
    id           SERIAL PRIMARY KEY
    url          TEXT UNIQUE NOT NULL
    title        TEXT
    http_status  INTEGER
    crawl_status TEXT   -- 'success' | 'failed' | 'skipped'
    crawled_at   TIMESTAMPTZ DEFAULT now()

Every URL the crawler attempts gets one row:
  - successful fetches  → crawl_status = 'success'
  - network / HTTP errors → crawl_status = 'failed'
  - duplicates / skipped  → crawl_status = 'skipped'  (optional, Phase 2 skips this)

The schema is intentionally minimal for Phase 2.  Additional columns
(domain, content_hash, canonical_url, etc.) will be added in later phases
via Alembic migrations.
"""

from datetime import datetime, timezone

from sqlalchemy import Integer, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from api.db.session import Base


class Page(Base):
    """
    ORM model for the `pages` table.

    Each row represents one crawl attempt for a unique URL.

    Attributes
    ----------
    id : int
        Auto-incrementing primary key.
    url : str
        The crawled URL.  Unique — one row per URL.
    title : str | None
        Page title extracted from the <title> tag, if present.
    http_status : int | None
        HTTP response status code (200, 404, 500, …).
        None if the request never completed (network error, timeout).
    crawl_status : str | None
        High-level outcome: 'success', 'failed', or 'skipped'.
    crawled_at : datetime
        UTC timestamp when this row was written.
    """

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)

    title: Mapped[str | None] = mapped_column(Text, nullable=True)

    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)

    crawl_status: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="'success' | 'failed' | 'skipped'",
    )

    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<Page id={self.id} status={self.crawl_status!r} url={self.url!r}>"
        )
