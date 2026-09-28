"""
routes/health.py — Health Check Endpoint (Phase 2)

GET /health  →  { "status": "ok" }

This is the simplest possible liveness probe.  Load balancers and
container orchestrators (Docker Compose healthcheck, Kubernetes liveness
probe) hit this endpoint to decide whether the service is up.

No database query is performed here — we only confirm the process is
alive and the event loop is responding.  A deeper readiness probe
(checking the DB connection) will be added in Phase 3.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health", tags=["Health"])
def health_check() -> JSONResponse:
    """
    Liveness check.

    Returns
    -------
    JSON
        ``{ "status": "ok" }`` with HTTP 200.
    """
    return JSONResponse(content={"status": "ok"})
