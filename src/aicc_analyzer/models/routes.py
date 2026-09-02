"""API routes for model-related endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/example")
async def example_endpoint() -> dict[str, str]:
    """Example API endpoint."""
    return {"message": "This is an example endpoint"}
