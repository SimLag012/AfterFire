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
        is_live = bool(settings.FIRMS_MAP_KEY)
        requires_cred = True
        msg = "Live NASA FIRMS Area API connected via FIRMS_MAP_KEY." if is_live else "FIRMS_MAP_KEY not set. Using calibrated historical demo data & CSV import mode."

    elif "MCD64A1" in dataset_id:
        c_res = await db.execute(select(func.count(BurnedAreaObservation.id)))
        count = c_res.scalar() or 0
        is_live = bool(settings.EARTHDATA_USERNAME and settings.EARTHDATA_PASSWORD)
        requires_cred = True
        msg = "NASA Earthdata authentication configured." if is_live else "Direct LP DAAC automated download requires Earthdata Login. Operating in cached / verified import mode."

    elif "MOD13Q1" in dataset_id:
        c_res = await db.execute(select(func.count(VegetationObservation.id)))
        count = c_res.scalar() or 0
        is_live = bool(settings.EARTHDATA_USERNAME and settings.EARTHDATA_PASSWORD)
        requires_cred = True
        msg = "NASA Earthdata authentication configured." if is_live else "Operating in calibrated time-series import mode."

    return DatasetStatusResponse(
        dataset_id=ds.id,
        name=ds.name,
        status=ds.status,
        record_count=count,
        is_live_api_configured=is_live,
        requires_credentials=requires_cred,
        connection_message=msg
    )

