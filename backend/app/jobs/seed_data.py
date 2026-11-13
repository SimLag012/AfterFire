import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.dataset import DatasetMetadata

logger = logging.getLogger(__name__)


async def seed_initial_data(session: AsyncSession):
    existing_datasets = await session.execute(select(DatasetMetadata))
    if not existing_datasets.scalars().first():
        datasets = [
            DatasetMetadata(
                id="FIRMS_MODIS_C61",
                name="NASA FIRMS MODIS Collection 6.1 (Terra/Aqua)",
                provider="NASA Earth Science Data and Information System (ESDIS) / FIRMS",
                official_url="https://firms.modaps.eosdis.nasa.gov/",
                version="Collection 6.1",
                spatial_resolution="1 km nominal (nadir)",
                temporal_frequency="4 daily passes (Terra & Aqua, Day & Night)",
                temporal_range="2000-present",
                status="active",
                limitations="Sub-pixel smoldering fires under dense cloud cover may be missed; 1km pixel may encompass multiple smaller flaming fronts.",
                citation="Giglio, L., Schroeder, W., & Justice, C. O. (2016). The collection 6 MODIS active fire detection algorithm and fire products. Remote Sensing of Environment, 178, 31-41."
            ),
            DatasetMetadata(
                id="FIRMS_VIIRS_375M",
                name="NASA FIRMS VIIRS 375m Active Fire (Suomi-NPP / NOAA-20 / NOAA-21)",
                provider="NASA ESDIS / FIRMS & NOAA",
                official_url="https://firms.modaps.eosdis.nasa.gov/",
                version="VNP14IMGTDL_NRT / Standard",
                spatial_resolution="375 m (I-band nadir)",
                temporal_frequency="4-6 daily passes combined constellation",
                temporal_range="2012-present",
                status="active",
                limitations="Higher spatial sensitivity produces approximately 3x-5x more detections than MODIS for the same fire perimeter.",
                citation="Schroeder, W., Oliva, P., Giglio, L., & Csiszar, I. A. (2014). The New VIIRS 375 m active fire detection product: Algorithm description and initial assessment. Remote Sensing of Environment, 143, 85-96."
            ),
            DatasetMetadata(
                id="MODIS_MCD64A1",
                name="MODIS MCD64A1 Monthly Burned Area Product",
                provider="NASA LP DAAC / USGS",
                official_url="https://lpdaac.usgs.gov/products/mcd64a1v061/",
                version="Version 061",
                spatial_resolution="500 m sinusoidal grid",
                temporal_frequency="Monthly composite with estimated day-of-year burn date",
                temporal_range="2000-present",
                status="active",
                limitations="500m grid cell may include unburned islands; temporal uncertainty can vary by ±2-4 days.",
                citation="Giglio, L., Boschetti, L., Roy, D. P., Humber, M. L., & Justice, C. O. (2018). The Collection 6 MODIS burned area mapping algorithm and product (MCD64A1). Remote Sensing of Environment, 217, 72-85."
            ),
            DatasetMetadata(
                id="MODIS_MOD13Q1",
                name="MODIS MOD13Q1 250m 16-Day Vegetation Indices (NDVI/EVI)",
                provider="NASA LP DAAC / USGS",
                official_url="https://lpdaac.usgs.gov/products/mod13q1v061/",
                version="Version 061",
                spatial_resolution="250 m sinusoidal grid",
                temporal_frequency="16-day composite",
                temporal_range="2000-present",
                status="active",
                limitations="NDVI saturates in dense multi-layered forest canopies; measures greenness, not biological biodiversity.",
                citation="Didan, K. (2015). MOD13Q1 MODIS/Terra Vegetation Indices 16-Day L3 Global 250m SIN Grid V006. NASA EOSDIS Land Processes DAAC."
            )
        ]
        session.add_all(datasets)
        await session.commit()
        logger.info("Seeded dataset metadata successfully.")
