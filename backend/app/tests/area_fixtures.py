import math
import logging
from datetime import datetime, date, timedelta
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.area import AreaOfInterest
from app.models.fire import FireDetection
from app.models.burned_area import BurnedAreaObservation
from app.models.vegetation import VegetationObservation
from app.models.event import FireEventCandidate
from app.models.recovery import RecoveryAnalysis

logger = logging.getLogger(__name__)


async def seed_sample_areas(session: AsyncSession):
    existing_areas = await session.execute(select(AreaOfInterest))
    if not existing_areas.scalars().first():
        areas = [
            AreaOfInterest(
                id="rhodes-greece-2023",
                name="Rhodes Island Wildfire Complex",
                description="Devastating Mediterranean pine and maquis forest wildfire in southern Rhodes (Laerma, Gennadi, Kiotari), July 2023.",
                country="Greece",
                min_lat=36.00,
                max_lat=36.25,
                min_lon=27.85,
                max_lon=28.18,
                center_lat=36.125,
                center_lon=28.015,
                area_km2=680.0,
                ecosystem_type="Mediterranean Pine Forest & Maquis",
                is_demo_preset="true"
            ),
            AreaOfInterest(
                id="jasper-canada-2024",
                name="Jasper National Park Wildfire Complex",
                description="High-intensity boreal and montane forest wildfire in Jasper National Park, Alberta, Canada, July-August 2024.",
                country="Canada",
                min_lat=52.75,
                max_lat=53.05,
                min_lon=-118.25,
                max_lon=-117.85,
                center_lat=52.90,
                center_lon=-118.05,
                area_km2=720.0,
                ecosystem_type="Boreal & Subalpine Coniferous Forest",
                is_demo_preset="true"
            ),
            AreaOfInterest(
                id="kangaroo-island-2020",
                name="Kangaroo Island Multi-Fire Complex",
                description="Black Summer bushfire crisis and recurring burn study on Kangaroo Island, South Australia (Flinders Chase National Park), 2019-2020.",
                country="Australia",
                min_lat=-35.95,
                max_lat=-35.70,
                min_lon=136.60,
                max_lon=137.05,
                center_lat=-35.825,
                center_lon=136.825,
                area_km2=890.0,
                ecosystem_type="Temperate Eucalyptus Woodland & Mallee",
                is_demo_preset="true"
            )
        ]
        session.add_all(areas)
        await session.commit()
        logger.info("Seeded areas of interest.")

        # Seed data for Rhodes Island 2023
        await _seed_rhodes_data(session)
        # Seed data for Jasper Canada 2024
        await _seed_jasper_data(session)
        # Seed data for Kangaroo Island 2020 (recurrent fire demonstration)
        await _seed_kangaroo_data(session)


async def _seed_rhodes_data(session: AsyncSession):
    area_id = "rhodes-greece-2023"
    fire_start = date(2023, 7, 18)
    
    # 1. Fire detections (MODIS and VIIRS across July 18-28, 2023)
    detections: List[FireDetection] = []
    
    # Generate realistic dual-sensor spread pattern
    base_lat = 36.12
    base_lon = 28.02
    
    for day_offset in range(11):
        cur_date = fire_start + timedelta(days=day_offset)
        # Intensity peaks around day 4-6 (July 22-24)
        intensity_mult = 1.0 + 3.0 * math.exp(-((day_offset - 5)**2) / 4.0)
        
        # VIIRS passes (higher resolution, more points)
        viirs_count = int(25 * intensity_mult)
        for i in range(viirs_count):
            lat_jitter = (hash(f"v_lat_{day_offset}_{i}") % 1000 - 500) / 5000.0 + (day_offset * 0.008)
            lon_jitter = (hash(f"v_lon_{day_offset}_{i}") % 1000 - 500) / 5000.0 - (day_offset * 0.006)
            frp_val = round(20.0 + (hash(f"v_frp_{day_offset}_{i}") % 400) * (intensity_mult / 2.0), 1)
            bright_val = round(315.0 + (hash(f"v_br_{day_offset}_{i}") % 60), 1)
            
            sat = "Suomi-NPP" if i % 2 == 0 else "NOAA-20"
            conf = "high" if frp_val > 100 else ("nominal" if frp_val > 35 else "low")
            
            det_id = f"VIIRS_RHODES_{cur_date.strftime('%Y%m%d')}_{i:03d}"
            detections.append(FireDetection(
                id=det_id,
                area_id=area_id,
                latitude=round(base_lat + lat_jitter, 5),
                longitude=round(base_lon + lon_jitter, 5),
                acq_date=cur_date,
                acq_time=f"{11 + (i % 3):02d}{15 + (i * 7) % 45:02d}",
                satellite=sat,
                instrument="VIIRS",
                confidence_raw=conf,
                confidence_level=conf,
                confidence_pct=90.0 if conf == "high" else (60.0 if conf == "nominal" else 20.0),
                frp=frp_val,
                brightness=bright_val,
                bright_t31=bright_val - 25.0,
                scan=0.38,
                track=0.38,
                daynight="D" if i % 4 != 0 else "N",
                dataset_name="FIRMS_VIIRS_VNP14IMGTDL",
                version="NRT/Archive",
                is_synthetic_demo="true"
            ))

        # MODIS passes (1km, lower count, higher integrated footprint)
        modis_count = int(8 * intensity_mult)
        for i in range(modis_count):
            lat_jitter = (hash(f"m_lat_{day_offset}_{i}") % 1000 - 500) / 4500.0 + (day_offset * 0.008)
            lon_jitter = (hash(f"m_lon_{day_offset}_{i}") % 1000 - 500) / 4500.0 - (day_offset * 0.006)
            frp_val = round(45.0 + (hash(f"m_frp_{day_offset}_{i}") % 600) * (intensity_mult / 2.0), 1)
            bright_val = round(320.0 + (hash(f"m_br_{day_offset}_{i}") % 50), 1)
            sat = "Terra" if i % 2 == 0 else "Aqua"
            conf_pct = float(min(100, 45 + (hash(f"m_c_{day_offset}_{i}") % 55)))
            conf_lvl = "high" if conf_pct >= 80 else ("nominal" if conf_pct >= 30 else "low")

            det_id = f"MODIS_RHODES_{cur_date.strftime('%Y%m%d')}_{i:03d}"
            detections.append(FireDetection(
                id=det_id,
                area_id=area_id,
                latitude=round(base_lat + lat_jitter, 5),
                longitude=round(base_lon + lon_jitter, 5),
                acq_date=cur_date,
                acq_time=f"{10 + (i % 4):02d}{20 + (i * 9) % 35:02d}",
                satellite=sat,
                instrument="MODIS",
                confidence_raw=str(int(conf_pct)),
                confidence_level=conf_lvl,
                confidence_pct=conf_pct,
                frp=frp_val,
                brightness=bright_val,
                bright_t31=bright_val - 30.0,
                scan=1.0,
                track=1.0,
                daynight="D" if i % 3 != 0 else "N",
                dataset_name="FIRMS_MODIS_C61",
                version="C6.1",
                is_synthetic_demo="true"
            ))

    session.add_all(detections)

    # 2. Burned area observations (MCD64A1 500m mapped burned pixels)
    burned_obs: List[BurnedAreaObservation] = []
    # July 2023 burned area ~ 13,500 hectares
    for px_idx in range(45):
        px_lat = base_lat + (px_idx % 8 - 4) * 0.015
        px_lon = base_lon + (px_idx // 8 - 3) * 0.015
        doy = 203 + (px_idx % 6)  # July 22-28
        b_date = date(2023, 1, 1) + timedelta(days=doy - 1)
        
        burned_obs.append(BurnedAreaObservation(
            id=f"MCD64A1_RHODES_2023_{px_idx:03d}",
            area_id=area_id,
            observation_date=date(2023, 8, 1),
            burn_date=b_date,
            burn_day_of_year=doy,
            latitude=round(px_lat, 5),
            longitude=round(px_lon, 5),
            area_hectares=300.0,  # Grouped pixel patches
            geometry_geojson=None,
            confidence=94.0,
            qa_flags="Valid clear post-burn reflectance change",
            uncertainty_days=2,
            sensor="MODIS",
            dataset_name="MCD64A1v061",
            version="061",
            is_synthetic_demo="true"
        ))
    session.add_all(burned_obs)

    # 3. Candidate Fire Event
    ev = FireEventCandidate(
        id="EVENT_rhodes-greece-2023_20230718_1",
        area_id=area_id,
        name="Rhodes Wildfire Crisis (July 2023)",
        start_date=date(2023, 7, 18),
        end_date=date(2023, 7, 28),
        duration_days=11,
        detection_count=len(detections),
        modis_detections=sum(1 for d in detections if d.instrument == "MODIS"),
        viirs_detections=sum(1 for d in detections if d.instrument == "VIIRS"),
        total_frp_mw=round(sum(d.frp for d in detections if d.frp), 1),
        max_frp_mw=max(d.frp for d in detections if d.frp),
        clustering_method="Spatiotemporal DBSCAN (5km radius, 3-day max gap)",
        estimated_fire_extent_km2=135.0,
        confidence_summary="Dual-sensor confirmed (high detection density)",
        notes="High-severity wildfire driven by heatwave Cerberus and strong Meltemi winds across south Rhodes.",
        is_synthetic_demo="true"
    )
    session.add(ev)

    # 4. MODIS MOD13Q1 Vegetation Index (NDVI) Time Series (2021-01 to 2024-10)
    # Calibrated to Mediterranean seasonality:
    # - Winter/Spring peak: 0.62 - 0.68
    # - Summer dry down: 0.44 - 0.48
    # - Post-fire drop (Aug 2023): drops to 0.17
    # - Recovery in 2024: rebounds to 0.38 - 0.42 (partial recovery / pioneer maquis)
    veg_obs: List[VegetationObservation] = []
    start_sim = date(2021, 1, 1)
    end_sim = date(2024, 10, 1)
    cur_d = start_sim

    while cur_d <= end_sim:
        doy = cur_d.timetuple().tm_yday
        # Natural Mediterranean seasonal curve
        seasonal_ndvi = 0.55 + 0.12 * math.cos(2 * math.pi * (doy - 80) / 365.25)
        
        # Fire disturbance effect
        if cur_d < date(2023, 7, 18):
            actual_ndvi = seasonal_ndvi + (hash(f"r_v_{cur_d}") % 100 - 50) / 2500.0
        elif cur_d < date(2023, 8, 15):
            # Immediate post-fire crash
            actual_ndvi = 0.17 + (hash(f"r_v_{cur_d}") % 50) / 2500.0
        else:
            # Months since fire
            months_after = (cur_d - date(2023, 8, 1)).days / 30.4
            # Recovery asymptote towards 0.70 of pre-fire baseline by late 2024
            rec_progress = 1.0 - math.exp(-months_after / 10.0)
            target_post = 0.17 + (seasonal_ndvi * 0.65 - 0.17) * rec_progress
            actual_ndvi = target_post + (hash(f"r_v_{cur_d}") % 80 - 40) / 2500.0

        scaled_ndvi = round(max(0.05, min(0.95, actual_ndvi)), 4)
        raw_val = int(scaled_ndvi * 10000)

        # Exclude occasional winter cloud / shadow
        is_cloud = (doy < 45 or doy > 330) and (hash(f"cloud_{cur_d}") % 10 == 0)
        qa_raw = 0b10 if is_cloud else 0b00
        qa_desc = "Excluded: Heavy cloud coverage / aerosol flag" if is_cloud else "Good quality (ideal observations)"

        veg_obs.append(VegetationObservation(
            id=f"MOD13Q1_RHODES_{cur_d.strftime('%Y%m%d')}",
            area_id=area_id,
            observation_date=cur_d,
            day_of_year=doy,
            year=cur_d.year,
            index_name="NDVI",
            raw_value=raw_val,
            scale_factor=0.0001,
            scaled_value=scaled_ndvi,
            std_dev=0.04,
            min_value=round(scaled_ndvi - 0.06, 4),
            max_value=round(scaled_ndvi + 0.06, 4),
            valid_pixel_pct=98.5 if not is_cloud else 42.0,
            qa_raw=qa_raw,
            qa_description=qa_desc,
            is_valid=not is_cloud,
            sensor="MODIS",
            satellite="Terra",
            dataset_name="MOD13Q1v061",
            version="061",
            is_synthetic_demo="true"
        ))

        cur_d += timedelta(days=16)

    session.add_all(veg_obs)
    await session.commit()
    logger.info("Rhodes data seeded.")


async def _seed_jasper_data(session: AsyncSession):
    area_id = "jasper-canada-2024"
    fire_start = date(2024, 7, 22)
    base_lat = 52.88
    base_lon = -118.06
    
    detections: List[FireDetection] = []
    for day_offset in range(12):
        cur_date = fire_start + timedelta(days=day_offset)
        intensity_mult = 1.0 + 3.5 * math.exp(-((day_offset - 4)**2) / 3.5)
        
        for i in range(int(18 * intensity_mult)):
            lat_jitter = (hash(f"j_lat_{day_offset}_{i}") % 1000 - 500) / 4000.0
            lon_jitter = (hash(f"j_lon_{day_offset}_{i}") % 1000 - 500) / 4000.0
            frp_val = round(30.0 + (hash(f"j_frp_{day_offset}_{i}") % 500) * intensity_mult, 1)
            bright_val = round(320.0 + (hash(f"j_br_{day_offset}_{i}") % 65), 1)
            conf = "high" if frp_val > 120 else "nominal"
            sat = "NOAA-20" if i % 2 == 0 else "Suomi-NPP"

            detections.append(FireDetection(
                id=f"VIIRS_JASPER_{cur_date.strftime('%Y%m%d')}_{i:03d}",
                area_id=area_id,
                latitude=round(base_lat + lat_jitter, 5),
                longitude=round(base_lon + lon_jitter, 5),
                acq_date=cur_date,
                acq_time=f"{13 + (i % 3):02d}{10 + (i * 7) % 45:02d}",
                satellite=sat,
                instrument="VIIRS",
                confidence_raw=conf,
                confidence_level=conf,
                confidence_pct=90.0 if conf == "high" else 60.0,
                frp=frp_val,
                brightness=bright_val,
                bright_t31=bright_val - 28.0,
                scan=0.38,
                track=0.38,
                daynight="D" if i % 4 != 0 else "N",
                dataset_name="FIRMS_VIIRS_VNP14IMGTDL",
                version="NRT/Archive",
                is_synthetic_demo="true"
            ))

        for i in range(int(6 * intensity_mult)):
            lat_jitter = (hash(f"jm_lat_{day_offset}_{i}") % 1000 - 500) / 3500.0
            lon_jitter = (hash(f"jm_lon_{day_offset}_{i}") % 1000 - 500) / 3500.0
            frp_val = round(60.0 + (hash(f"jm_frp_{day_offset}_{i}") % 700) * intensity_mult, 1)
            bright_val = round(325.0 + (hash(f"jm_br_{day_offset}_{i}") % 55), 1)
            sat = "Terra" if i % 2 == 0 else "Aqua"
            conf_pct = float(min(100, 50 + (hash(f"jm_c_{day_offset}_{i}") % 50)))

            detections.append(FireDetection(
                id=f"MODIS_JASPER_{cur_date.strftime('%Y%m%d')}_{i:03d}",
                area_id=area_id,
                latitude=round(base_lat + lat_jitter, 5),
                longitude=round(base_lon + lon_jitter, 5),
                acq_date=cur_date,
                acq_time=f"{12 + (i % 4):02d}{18 + (i * 8) % 38:02d}",
                satellite=sat,
                instrument="MODIS",
                confidence_raw=str(int(conf_pct)),
                confidence_level="high" if conf_pct >= 80 else "nominal",
                confidence_pct=conf_pct,
                frp=frp_val,
                brightness=bright_val,
                bright_t31=bright_val - 32.0,
                scan=1.0,
                track=1.0,
                daynight="D" if i % 3 != 0 else "N",
                dataset_name="FIRMS_MODIS_C61",
                version="C6.1",
                is_synthetic_demo="true"
            ))
    session.add_all(detections)

    # Jasper Candidate Event
    ev = FireEventCandidate(
        id="EVENT_jasper-canada-2024_20240722_1",
        area_id=area_id,
        name="Jasper National Park Wildfire Complex (2024)",
        start_date=date(2024, 7, 22),
        end_date=date(2024, 8, 2),
        duration_days=12,
        detection_count=len(detections),
        modis_detections=sum(1 for d in detections if d.instrument == "MODIS"),
        viirs_detections=sum(1 for d in detections if d.instrument == "VIIRS"),
        total_frp_mw=round(sum(d.frp for d in detections if d.frp), 1),
        max_frp_mw=max(d.frp for d in detections if d.frp),
        clustering_method="Spatiotemporal DBSCAN (5km radius, 3-day max gap)",
        estimated_fire_extent_km2=320.0,
        confidence_summary="High-intensity crown fire cluster",
        notes="Extreme pyrocumulonimbus fire run through lodgepole pine stands into Athabasca River valley.",
        is_synthetic_demo="true"
    )
    session.add(ev)

    # Burned area MCD64A1
    burned_obs = []
    for px_idx in range(60):
        px_lat = base_lat + (px_idx % 10 - 5) * 0.018
        px_lon = base_lon + (px_idx // 10 - 3) * 0.018
        doy = 206 + (px_idx % 8)
        b_date = date(2024, 1, 1) + timedelta(days=doy - 1)
        burned_obs.append(BurnedAreaObservation(
            id=f"MCD64A1_JASPER_2024_{px_idx:03d}",
            area_id=area_id,
            observation_date=date(2024, 8, 1),
            burn_date=b_date,
            burn_day_of_year=doy,
            latitude=round(px_lat, 5),
            longitude=round(px_lon, 5),
            area_hectares=530.0,
            geometry_geojson=None,
            confidence=96.0,
            qa_flags="Clear spectral burn signal; confirmed post-fire char",
            uncertainty_days=1,
            sensor="MODIS",
            dataset_name="MCD64A1v061",
            version="061",
            is_synthetic_demo="true"
        ))
    session.add_all(burned_obs)

    # Boreal NDVI time-series (winter snow exclusion QA!)
    veg_obs: List[VegetationObservation] = []
    start_sim = date(2022, 1, 1)
    end_sim = date(2024, 10, 1)
    cur_d = start_sim

    while cur_d <= end_sim:
        doy = cur_d.timetuple().tm_yday
        # Boreal summer peak in July (doy 200), winter snow cover (doy < 90 or doy > 300)
        is_snow = doy < 90 or doy > 300
        seasonal_ndvi = 0.72 + 0.08 * math.cos(2 * math.pi * (doy - 200) / 365.25)

        if cur_d < date(2024, 7, 22):
            actual_ndvi = seasonal_ndvi + (hash(f"j_v_{cur_d}") % 80 - 40) / 2500.0
        else:
            # Recent crash in July 2024
            actual_ndvi = 0.14 + (hash(f"j_v_{cur_d}") % 50) / 2500.0

        scaled_ndvi = round(max(0.02, min(0.95, actual_ndvi)), 4)
        raw_val = int(scaled_ndvi * 10000)

        qa_raw = 0b100000000000000 if is_snow else 0b00  # bit 14 snow
        qa_desc = "Excluded: Snow/Ice contamination flag set" if is_snow else "Good quality (ideal observations)"

        veg_obs.append(VegetationObservation(
            id=f"MOD13Q1_JASPER_{cur_d.strftime('%Y%m%d')}",
            area_id=area_id,
            observation_date=cur_d,
            day_of_year=doy,
            year=cur_d.year,
            index_name="NDVI",
            raw_value=raw_val,
            scale_factor=0.0001,
            scaled_value=scaled_ndvi,
            std_dev=0.05,
            min_value=round(scaled_ndvi - 0.07, 4),
            max_value=round(scaled_ndvi + 0.07, 4),
            valid_pixel_pct=99.0 if not is_snow else 25.0,
            qa_raw=qa_raw,
            qa_description=qa_desc,
            is_valid=not is_snow,
            sensor="MODIS",
            satellite="Terra",
            dataset_name="MOD13Q1v061",
            version="061",
            is_synthetic_demo="true"
        ))
        cur_d += timedelta(days=16)

    session.add_all(veg_obs)
    await session.commit()
    logger.info("Jasper data seeded.")


async def _seed_kangaroo_data(session: AsyncSession):
    """
    Kangaroo Island: Demonstrates recurring fire / compound disturbance!
    Event 1: Dec 20, 2019
    Event 2: Jan 03, 2020 (re-burn / fire expansion before any recovery!)
    """
    area_id = "kangaroo-island-2020"
    base_lat = -35.83
    base_lon = 136.83
    
    # Event 1 (Dec 2019)
    ev1_date = date(2019, 12, 20)
    dets: List[FireDetection] = []
    
    for offset in range(5):
        d = ev1_date + timedelta(days=offset)
        for i in range(12):
            lat_jitter = (hash(f"k1_lat_{offset}_{i}") % 1000 - 500) / 4000.0
            lon_jitter = (hash(f"k1_lon_{offset}_{i}") % 1000 - 500) / 4000.0
            dets.append(FireDetection(
                id=f"VIIRS_KI_EV1_{d.strftime('%Y%m%d')}_{i:03d}",
                area_id=area_id,
                latitude=round(base_lat + lat_jitter, 5),
                longitude=round(base_lon + lon_jitter, 5),
                acq_date=d,
                acq_time=f"{2 + (i % 3):02d}{15 + (i * 7) % 45:02d}",
                satellite="Suomi-NPP",
                instrument="VIIRS",
                confidence_raw="high",
                confidence_level="high",
                confidence_pct=92.0,
                frp=120.0 + (hash(f"k1_f_{offset}_{i}") % 250),
                brightness=335.0,
                bright_t31=305.0,
                scan=0.38,
                track=0.38,
                daynight="D",
                dataset_name="FIRMS_VIIRS_VNP14IMGTDL",
                version="Standard",
                is_synthetic_demo="true"
            ))

    # Event 2 (Jan 03, 2020 - major catastrophic expansion)
    ev2_date = date(2020, 1, 3)
    for offset in range(8):
        d = ev2_date + timedelta(days=offset)
        for i in range(25):
            lat_jitter = (hash(f"k2_lat_{offset}_{i}") % 1000 - 500) / 3500.0 + 0.02
            lon_jitter = (hash(f"k2_lon_{offset}_{i}") % 1000 - 500) / 3500.0 + 0.015
            dets.append(FireDetection(
                id=f"VIIRS_KI_EV2_{d.strftime('%Y%m%d')}_{i:03d}",
                area_id=area_id,
                latitude=round(base_lat + lat_jitter, 5),
                longitude=round(base_lon + lon_jitter, 5),
                acq_date=d,
                acq_time=f"{3 + (i % 3):02d}{10 + (i * 6) % 45:02d}",
                satellite="NOAA-20",
                instrument="VIIRS",
                confidence_raw="high",
                confidence_level="high",
                confidence_pct=95.0,
                frp=250.0 + (hash(f"k2_f_{offset}_{i}") % 500),
                brightness=348.0,
                bright_t31=310.0,
                scan=0.38,
                track=0.38,
                daynight="D",
                dataset_name="FIRMS_VIIRS_VNP14IMGTDL",
                version="Standard",
                is_synthetic_demo="true"
            ))
    session.add_all(dets)

    # 2 Events
    session.add(FireEventCandidate(
        id="EVENT_kangaroo-island-2020_20191220_1",
        area_id=area_id,
        name="Ravine des Casoars Fire (Dec 2019)",
        start_date=ev1_date,
        end_date=ev1_date + timedelta(days=5),
        duration_days=6,
        detection_count=60,
        modis_detections=15,
        viirs_detections=45,
        total_frp_mw=8450.0,
        max_frp_mw=370.0,
        clustering_method="Spatiotemporal DBSCAN (5km radius, 3-day max gap)",
        estimated_fire_extent_km2=180.0,
        confidence_summary="Initial lightning ignition cluster",
        notes="First lightning storm ignition in western Flinders Chase.",
        is_synthetic_demo="true"
    ))
    session.add(FireEventCandidate(
        id="EVENT_kangaroo-island-2020_20200103_2",
        area_id=area_id,
        name="Black Summer Mega-Fire Blowup (Jan 2020)",
        start_date=ev2_date,
        end_date=ev2_date + timedelta(days=8),
        duration_days=9,
        detection_count=200,
        modis_detections=50,
        viirs_detections=150,
        total_frp_mw=34200.0,
        max_frp_mw=890.0,
        clustering_method="Spatiotemporal DBSCAN (5km radius, 3-day max gap)",
        estimated_fire_extent_km2=680.0,
        confidence_summary="Compound blow-up event",
        notes="Catastrophic southwest wind change merged flanks across the entire western half of the island before any vegetation recovery.",
        is_synthetic_demo="true"
    ))

    # Burned area
    session.add(BurnedAreaObservation(
        id="MCD64A1_KI_2020_001",
        area_id=area_id,
        observation_date=date(2020, 1, 15),
        burn_date=date(2020, 1, 4),
        burn_day_of_year=4,
        latitude=base_lat,
        longitude=base_lon,
        area_hectares=48000.0,
        geometry_geojson=None,
        confidence=98.0,
        qa_flags="Total canopy consumption mapped",
        uncertainty_days=1,
        sensor="MODIS",
        dataset_name="MCD64A1v061",
        version="061",
        is_synthetic_demo="true"
    ))

    # NDVI time series (2018 to 2023) showing compound disturbance and eucalyptus resprouting
    veg_obs: List[VegetationObservation] = []
    start_sim = date(2018, 1, 1)
    end_sim = date(2023, 12, 1)
    cur_d = start_sim

    while cur_d <= end_sim:
        doy = cur_d.timetuple().tm_yday
        seasonal_ndvi = 0.64 + 0.09 * math.cos(2 * math.pi * (doy - 240) / 365.25)
        
        if cur_d < date(2019, 12, 20):
            actual_ndvi = seasonal_ndvi
        elif cur_d < date(2020, 1, 20):
            # Severe crash
            actual_ndvi = 0.12
        else:
            # Epicormic resprouting over 3 years
            months_after = (cur_d - date(2020, 1, 15)).days / 30.4
            rec_progress = 1.0 - math.exp(-months_after / 18.0)
            target = 0.12 + (seasonal_ndvi - 0.12) * rec_progress
            actual_ndvi = target

        scaled_ndvi = round(max(0.05, min(0.95, actual_ndvi)), 4)
        veg_obs.append(VegetationObservation(
            id=f"MOD13Q1_KI_{cur_d.strftime('%Y%m%d')}",
            area_id=area_id,
            observation_date=cur_d,
            day_of_year=doy,
            year=cur_d.year,
            index_name="NDVI",
            raw_value=int(scaled_ndvi * 10000),
            scale_factor=0.0001,
            scaled_value=scaled_ndvi,
            std_dev=0.03,
            min_value=round(scaled_ndvi - 0.05, 4),
            max_value=round(scaled_ndvi + 0.05, 4),
            valid_pixel_pct=99.0,
            qa_raw=0,
            qa_description="Good quality (ideal observations)",
            is_valid=True,
            sensor="MODIS",
            satellite="Terra",
            dataset_name="MOD13Q1v061",
            version="061",
            is_synthetic_demo="true"
        ))
        cur_d += timedelta(days=16)

    session.add_all(veg_obs)
    await session.commit()
    logger.info("Kangaroo Island data seeded.")
