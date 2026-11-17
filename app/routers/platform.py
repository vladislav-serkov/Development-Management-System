"""Facts about the platform itself: who looks after it, subscription limits."""
from fastapi import APIRouter

from app.config import settings
from app.services import codex_limits

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/support")
async def support_contact():
    """Whom to contact when the platform cannot reach the stand or breaks."""
    return {"name": settings.support_contact_name or None, "url": settings.support_contact_url or None}


@router.get("/codex-limits")
async def codex_usage_limits(refresh: bool = False):
    """Usage windows of the ChatGPT subscription behind every Codex workflow."""
    return await codex_limits.get_limits(refresh=refresh)
