"""Unauthenticated liveness endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Report that the process is up."""
    return {"status": "ok"}
