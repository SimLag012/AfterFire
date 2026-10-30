import json
import math
from datetime import date, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from shapely import prepare
from shapely.geometry import Point, Polygon, box, shape
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fire import FireDetection
from app.models.import_metadata import FirmsImportCheckpoint

BOUNDARY_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "natural_earth_5_1_2_italy.geojson"
)

PRODUCTS: dict[str, dict[str, str]] = {
    "FIRMS_MODIS_C61": {
        "name": "MODIS Collection 6.1 active fire",
        "instrument": "MODIS",
        "satellites": "Terra, Aqua",
        "archive_product": "MODIS_C6_1",
        "recent_api_source": "MODIS_NRT",
    },
    "FIRMS_VIIRS_SNPP_375M": {
        "name": "VIIRS 375 m active fire",
        "instrument": "VIIRS",
        "satellites": "Suomi-NPP",
        "archive_product": "VIIRS_SNPP_SP",
        "recent_api_source": "VIIRS_SNPP_NRT",
    },
    "FIRMS_VIIRS_NOAA20_375M": {
        "name": "VIIRS 375 m active fire",
        "instrument": "VIIRS",
        "satellites": "NOAA-20",
        "archive_product": "VIIRS_NOAA20_SP",
        "recent_api_source": "VIIRS_NOAA20_NRT",
    },
    "FIRMS_VIIRS_NOAA21_375M": {
        "name": "VIIRS 375 m active fire",
        "instrument": "VIIRS",
        "satellites": "NOAA-21",
        "archive_product": "VIIRS_NOAA21_SP",
        "recent_api_source": "VIIRS_NOAA21_NRT",
    },
}

PRODUCTS["FIRMS_MODIS_ANNUAL"] = {
    **PRODUCTS["FIRMS_MODIS_C61"], "name": "MODIS annual country archive (original FIRMS versions retained)",
    "archive_product": "MODIS_ANNUAL", "recent_api_source": "",
}


@lru_cache(maxsize=1)
def italy_geometry():
    with BOUNDARY_PATH.open(encoding="utf-8") as stream:
        collection = json.load(stream)
    if collection.get("name") != "Natural Earth v5.1.2 ne_10m_admin_0_countries (Italy only)":
        raise RuntimeError("The bundled Italy boundary is not the expected Natural Earth v5.1.2 asset.")
    features = collection.get("features", [])
    if len(features) != 1 or features[0].get("properties", {}).get("ADMIN") != "Italy":
        raise RuntimeError("The bundled Natural Earth asset does not contain exactly Italy.")
    geometry = shape(features[0]["geometry"])
    prepare(geometry)
    return geometry


def point_is_in_italy(latitude: float, longitude: float) -> bool:
    return italy_geometry().covers(Point(longitude, latitude))


def bbox_intersects_italy(west: float, south: float, east: float, north: float) -> bool:
    return italy_geometry().intersects(box(west, south, east, north))


async def import_checkpoints(db: AsyncSession) -> list[FirmsImportCheckpoint]:
    result = await db.execute(
        select(FirmsImportCheckpoint).order_by(FirmsImportCheckpoint.last_import_at.desc())
    )
    return list(result.scalars().all())


async def coverage_status_for_query(
    db: AsyncSession,
    west: float,
    south: float,
    east: float,
    north: float,
    start_date: date | None,
    end_date: date | None,
    matching_observations: int,
    center_lat: float | None = None,
    center_lon: float | None = None,
    radius_km: float | None = None,
) -> dict[str, Any]:
    italy = italy_geometry()
    query_geometry = box(west, south, east, north) if west < east else box(west, south, 180, north).union(box(-180, south, east, north))
    if radius_km is not None:
        lat, lon = math.radians(center_lat), math.radians(center_lon)
        angle = radius_km / 6371.0088
        points = []
        for bearing in range(0, 361, 2):
            azimuth = math.radians(bearing)
            latitude = math.asin(math.sin(lat) * math.cos(angle) + math.cos(lat) * math.sin(angle) * math.cos(azimuth))
            longitude = lon + math.atan2(math.sin(azimuth) * math.sin(angle) * math.cos(lat), math.cos(angle) - math.sin(lat) * math.sin(latitude))
            points.append((math.degrees(longitude), math.degrees(latitude)))
        query_geometry = Polygon(points)
    partial = not italy.covers(query_geometry)
    if matching_observations:
        state = "observations_present"
        detail = "Available local observations match this query."
        if partial:
            detail += " Geographic coverage is incomplete: imported coverage is Italy only."
    elif not italy.intersects(query_geometry):
        state = "outside_italy"
        detail = "No data available in the current local archive for this area and period. Imported coverage is Italy only."
    else:
        checkpoints = await import_checkpoints(db)
        overlaps_loaded_window = any(
            c.min_date is not None and c.max_date is not None
            and (end_date is None or c.min_date <= end_date)
            and (start_date is None or c.max_date >= start_date)
            and c.imported_count > 0 for c in checkpoints
        )
        state = "no_matching_observations_in_loaded_product_windows" if overlaps_loaded_window else "uncovered_or_unverified"
        detail = "No data available in the current local archive for this area and period. Absence of records is not evidence that no fires occurred."
        if partial:
            detail += " Geographic coverage is incomplete: imported coverage is Italy only."
    return {
        "status": state,
        "partial": partial,
        "matching_real_observations": matching_observations,
        "detail": detail,
        "completeness": "not_assessed",
    }


async def build_italy_coverage(db: AsyncSession, map_key_configured: bool) -> dict[str, Any]:
    rows = (await db.execute(select(
        FireDetection.dataset_name, FireDetection.instrument, FireDetection.satellite,
        FireDetection.is_synthetic_demo, func.count().label("count"),
        func.min(FireDetection.acq_date).label("min_date"),
        func.max(FireDetection.acq_date).label("max_date"),
        func.max(FireDetection.created_at).label("last_import_at"),
    ).where(FireDetection.import_region == "Italy").group_by(
        FireDetection.dataset_name, FireDetection.instrument, FireDetection.satellite,
        FireDetection.is_synthetic_demo,
    ))).all()
    checkpoints = await import_checkpoints(db)

    def summarize(synthetic: bool) -> dict[str, Any]:
        selected = [r for r in rows if (r.is_synthetic_demo == "true") == synthetic]
        def summary(group):
            return dict(count=sum(r.count for r in group),
                        sensors=sorted({r.instrument for r in group}),
                        satellites=sorted({r.satellite for r in group}),
                        min_date=str(min(r.min_date for r in group)) if group else None,
                        max_date=str(max(r.max_date for r in group)) if group else None,
                        last_import_at=max((r.last_import_at for r in group if r.last_import_at), default=None))
        result = summary(selected)
        result["products"] = [dict(dataset_name=name, **summary([r for r in selected if r.dataset_name == name]))
                              for name in sorted({r.dataset_name for r in selected})]
        for item in [result, *result["products"]]:
            if item["last_import_at"]:
                item["last_import_at"] = item["last_import_at"].replace(tzinfo=timezone.utc).isoformat()
        return result

    real_summary, demo_summary = summarize(False), summarize(True)
    demo_total = await db.scalar(select(func.count(FireDetection.id)).where(FireDetection.is_synthetic_demo == "true")) or 0
    demo_summary["database_demo_count_outside_italy_included"] = demo_total - demo_summary["count"]

    product_state = []
    for product_id, details in PRODUCTS.items():
        imported = next(
            (item for item in real_summary["products"] if item["dataset_name"] == product_id),
            None,
        )
        product_checkpoints = [
            row for row in checkpoints
            if product_id in json.loads(row.products_json or "[]")
        ]
        latest_checkpoint = max(
            product_checkpoints, key=lambda row: row.last_import_at, default=None
        )
        product_state.append({
            "dataset_name": product_id,
            **details,
            "source_configured": bool(map_key_configured),
            "historical_archive_import": "csv_file_import_supported",
            "recent_api": (
                "supported_with_map_key"
                if details["recent_api_source"] and map_key_configured
                else "supported_but_map_key_missing"
                if details["recent_api_source"]
                else "not_supported_by_recent_area_api"
            ),
            "loaded_count": imported["count"] if imported else 0,
            "loaded_min_date": imported["min_date"] if imported else None,
            "loaded_max_date": imported["max_date"] if imported else None,
            "last_import_at": latest_checkpoint.last_import_at.replace(tzinfo=timezone.utc).isoformat()
            if latest_checkpoint else imported["last_import_at"] if imported else None,
            "coverage_status": latest_checkpoint.coverage_status
            if latest_checkpoint else "no_import_metadata",
        })

    return {
        "region": "Italy",
        "boundary": {
            "source": "Natural Earth",
            "version": "5.1.2",
            "asset": "backend/data/natural_earth_5_1_2_italy.geojson",
            "attribution": "Natural Earth, 1:10m cultural vectors, Admin-0 Countries. Public domain.",
        },
        "completeness": "not_assessed",
        "configured_sources": {
            "nasa_firms_map_key_configured": bool(map_key_configured),
            "historical_archive_csv_import": "supported",
            "recent_area_api": "configured" if map_key_configured else "unconfigured",
        },
        "real": real_summary,
        "demo": {
            **demo_summary,
            "scope_note": "Synthetic rows are reported separately and are never counted as real Italy coverage.",
        },
        "products": product_state,
        "imports": [
            {
                "source_file": row.source_file,
                "status": row.status,
                "coverage_status": row.coverage_status,
                "products": json.loads(row.products_json or "[]"),
                "processed_rows": row.processed_rows,
                "imported_count": row.imported_count,
                "invalid_count": row.invalid_count,
                "outside_count": row.outside_count,
                "duplicate_count": row.duplicate_count,
                "min_date": str(row.min_date) if row.min_date else None,
                "max_date": str(row.max_date) if row.max_date else None,
                "last_import_at": row.last_import_at.replace(tzinfo=timezone.utc).isoformat(),
            }
            for row in checkpoints
        ],
    }
