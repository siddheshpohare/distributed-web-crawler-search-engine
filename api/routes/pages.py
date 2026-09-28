"""
routes/pages.py — Page Query Endpoints (Phase 2)

Routes:
    GET /api/v1/pages          List all crawled pages (paginated).
    GET /api/v1/pages/{id}     Get a single page record by database ID.

Both endpoints read from the `pages` PostgreSQL table and return
results shaped by the PageResponse Pydantic schema.

Pagination
──────────
GET /api/v1/pages accepts two optional query parameters:
    skip  : int  — number of rows to skip (offset).  Default 0.
    limit : int  — maximum rows to return.  Default 20, max 100.

Example:
    GET /api/v1/pages?skip=0&limit=20   → first 20 pages
    GET /api/v1/pages?skip=20&limit=20  → next 20 pages
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.db.session import get_db
from api.db.models import Page
from api.schemas import PageResponse

router = APIRouter(prefix="/api/v1", tags=["Pages"])


# ── GET /api/v1/pages ─────────────────────────────────────────────────────────

@router.get("/pages", response_model=list[PageResponse])
def list_pages(
    skip: int = Query(default=0, ge=0, description="Number of rows to skip."),
    limit: int = Query(default=20, ge=1, le=100, description="Max rows to return (1–100)."),
    db: Session = Depends(get_db),
) -> list[PageResponse]:
    """
    Return a paginated list of crawled pages.

    Pages are ordered by ``id`` ascending (oldest first).

    Parameters
    ----------
    skip : int
        Offset — skip this many rows before returning results.
    limit : int
        Page size — return at most this many rows.

    Returns
    -------
    list[PageResponse]
        List of page records.
    """
    rows = (
        db.query(Page)
        .order_by(Page.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return rows   # Pydantic's from_attributes=True converts ORM rows automatically.


# ── GET /api/v1/pages/{id} ────────────────────────────────────────────────────

@router.get("/pages/{page_id}", response_model=PageResponse)
def get_page(page_id: int, db: Session = Depends(get_db)) -> PageResponse:
    """
    Return a single page record by its database ID.

    Parameters
    ----------
    page_id : int
        The ``id`` column value of the page to retrieve.

    Returns
    -------
    PageResponse
        The matching page record.

    Raises
    ------
    HTTPException 404
        If no page with the given ID exists.
    """
    row = db.query(Page).filter(Page.id == page_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Page with id={page_id} not found.")
    return row
