from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.database import get_db
from app.models.dataset import DatasetMetadata
from app.models.fire import FireDetection
from app.models.burned_area import BurnedAreaObservation
from app.models.vegetation import VegetationObservation
from app.schemas.dataset import DatasetMetadataResponse, DatasetStatusResponse
from app.core.config import settings
from app.providers.firms import FirmsProvider

router = APIRouter()


@router.get("/datasets", response_model=List[DatasetMetadataResponse])
async def list_datasets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DatasetMetadata))
    datasets = result.scalars().all()
    return datasets


@router.get("/datasets/{dataset_id}/status", response_model=DatasetStatusResponse)
async def get_dataset_status(dataset_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DatasetMetadata).filter(DatasetMetadata.id == dataset_id))
    ds = result.scalars().first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    count = 0
    is_live = False
    requires_cred = False
    msg = ""

    if "FIRMS" in dataset_id:
        c_res = await db.execute(select(func.count(FireDetection.id)).filter(FireDetection.dataset_name.contains(ds.name[:10])))
        count = c_res.scalar() or 0
        firms_status = await FirmsProvider.check_connectivity(force=False)
        is_live = firms_status["connected"]
        requires_cred = True
        msg = firms_status["message"]

    elif "MCD64A1" in dataset_id:
        c_res = await db.execute(select(func.count(BurnedAreaObservation.id)))
        count = c_res.scalar() or 0
        has_earthdata = bool(settings.EARTHDATA_USERNAME and settings.EARTHDATA_PASSWORD)
        is_live = False
        requires_cred = True
        msg = (
            "NASA Earthdata credentials configured. Validated CSV/HDF file ingestion supported; automated regional subsetting download is not available."
            if has_earthdata
            else "NASA Earthdata login not configured. Operating in verified import / historical sample mode."
        )

    elif "MOD13Q1" in dataset_id:
        c_res = await db.execute(select(func.count(VegetationObservation.id)))
        count = c_res.scalar() or 0
        has_earthdata = bool(settings.EARTHDATA_USERNAME and settings.EARTHDATA_PASSWORD)
        is_live = False
        requires_cred = True
        msg = (
            "NASA Earthdata credentials configured. Supports ingestion and 16-bit QA bitmask parsing for MOD13Q1 250m composites."
            if has_earthdata
            else "NASA Earthdata login not configured. Operating in verified import / historical sample mode."
        )

    return DatasetStatusResponse(
        dataset_id=ds.id,
        name=ds.name,
        status=ds.status,
        record_count=count,
        is_live_api_configured=is_live,
        requires_credentials=requires_cred,
        connection_message=msg
    )

