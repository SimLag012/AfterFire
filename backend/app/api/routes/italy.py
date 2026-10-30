from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.services.italy_coverage import build_italy_coverage

router = APIRouter()


@router.get("/italy/coverage")
async def italy_coverage(db: AsyncSession = Depends(get_db)):
    """Report observed database coverage without implying complete history."""
    return await build_italy_coverage(db, bool(settings.FIRMS_MAP_KEY.strip()))
