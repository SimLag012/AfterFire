#!/usr/bin/env python3
"""Import or update FIRMS observations for Italy; archive imports are resumable."""

import argparse
import ast
import asyncio
import csv
import hashlib
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.config import settings
from app.db.database import AsyncSessionLocal, engine, init_db
from app.models.fire import FireDetection
from app.models.import_metadata import FirmsImportCheckpoint
from app.providers.firms import FirmsProvider
from app.services.italy_coverage import PRODUCTS, point_is_in_italy

PRODUCT_ALIASES = {
    "MODIS_ANNUAL": "FIRMS_MODIS_ANNUAL",
    "MODIS_C6_1": "FIRMS_MODIS_C61",
    "MODIS_C61": "FIRMS_MODIS_C61",
    "VIIRS_SNPP_SP": "FIRMS_VIIRS_SNPP_375M",
    "VIIRS_NOAA20_SP": "FIRMS_VIIRS_NOAA20_375M",
    "VIIRS_NOAA21_SP": "FIRMS_VIIRS_NOAA21_375M",
}
SATELLITES = {
    "FIRMS_MODIS_C61": {
        "T": "Terra", "TERRA": "Terra", "EOS-TERRA": "Terra",
        "TERRA (EOS AM-1)": "Terra", "A": "Aqua", "AQUA": "Aqua",
        "EOS-AQUA": "Aqua", "AQUA (EOS PM-1)": "Aqua",
    },
    "FIRMS_VIIRS_SNPP_375M": {
        "N": "Suomi-NPP", "SNPP": "Suomi-NPP", "SUOMI-NPP": "Suomi-NPP",
        "SUOMI NPP": "Suomi-NPP",
    },
    "FIRMS_VIIRS_NOAA20_375M": {
        "1": "NOAA-20", "J1": "NOAA-20", "N20": "NOAA-20", "NOAA20": "NOAA-20", "NOAA-20": "NOAA-20",
        "JPSS-1": "NOAA-20",
    },
    "FIRMS_VIIRS_NOAA21_375M": {
        "2": "NOAA-21", "J2": "NOAA-21", "N21": "NOAA-21", "NOAA21": "NOAA-21", "NOAA-21": "NOAA-21",
        "JPSS-2": "NOAA-21",
    },
}
SATELLITES["FIRMS_MODIS_ANNUAL"] = SATELLITES["FIRMS_MODIS_C61"]
REQUIRED_COLUMNS = {"latitude", "longitude", "acq_date", "acq_time", "satellite"}
CHUNK_SIZE_DEFAULT = 1000


class InvalidArchiveRow(ValueError):
    pass


def product_id(value: str) -> str:
    key = value.strip().upper()
    key = PRODUCT_ALIASES.get(key, key)
    if key not in PRODUCTS:
        raise ValueError(f"Unsupported FIRMS product: {value}")
    return key


def _normalized_record(row: dict[str, str], product: str) -> dict:
    row = {str(key).strip().lower(): value for key, value in row.items()}
    missing = REQUIRED_COLUMNS - {key.lower() for key in row}
    if missing:
        raise InvalidArchiveRow(f"missing required values: {', '.join(sorted(missing))}")
    try:
        latitude = float(row["latitude"])
        longitude = float(row["longitude"])
        if not math.isfinite(latitude) or not -90 <= latitude <= 90:
            raise ValueError
        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise InvalidArchiveRow("invalid WGS84 coordinates") from exc

    try:
        raw_acquired = row["acq_date"]
        acquired = raw_acquired if isinstance(raw_acquired, date) else date.fromisoformat(str(raw_acquired).strip())
    except (AttributeError, ValueError) as exc:
        raise InvalidArchiveRow("acq_date must use YYYY-MM-DD") from exc
    time_raw = str(row.get("acq_time", "")).strip()
    if (
        not time_raw.isdigit()
        or len(time_raw) > 4
        or int(time_raw) // 100 > 23
        or int(time_raw) % 100 > 59
    ):
        raise InvalidArchiveRow("acq_time must be a valid HHMM value")
    satellite_raw = str(row.get("satellite", "")).strip().upper()
    satellite = SATELLITES[product].get(satellite_raw)
    if not satellite:
        raise InvalidArchiveRow(f"satellite {satellite_raw!r} does not match product {product}")

    instrument = PRODUCTS[product]["instrument"]
    row_instrument = str(row.get("instrument", "")).strip().upper()
    if row_instrument and row_instrument != instrument:
        raise InvalidArchiveRow(f"instrument {row_instrument!r} does not match product {product}")

    raw_confidence = row.get("confidence", row.get("confidence_raw"))
    if raw_confidence not in (None, ""):
        try:
            confidence = float(raw_confidence)
        except (ValueError, TypeError):
            if str(raw_confidence).strip().lower() not in {"l", "n", "h", "low", "nominal", "high"}:
                raise InvalidArchiveRow("invalid confidence category")
        else:
            if not math.isfinite(confidence) or not 0 <= confidence <= 100:
                raise InvalidArchiveRow("confidence must be between 0 and 100")
    if row.get("daynight") not in (None, "") and str(row["daynight"]).strip().upper() not in {"D", "N"}:
        raise InvalidArchiveRow("daynight must be D or N")

    normalized = dict(row)
    if "confidence" not in normalized and row.get("confidence_raw") is not None:
        normalized["confidence"] = row["confidence_raw"]
    for key in ("frp", "brightness", "bright_ti4", "bright_t31", "bright_ti5", "scan", "track"):
        if row.get(key) not in (None, ""):
            try:
                value = float(row[key])
            except (ValueError, TypeError) as exc:
                raise InvalidArchiveRow(f"invalid {key}") from exc
            if not math.isfinite(value) or value < 0:
                raise InvalidArchiveRow(f"invalid {key}")
    normalized.update({
        "latitude": str(latitude),
        "longitude": str(longitude),
        "acq_date": acquired.isoformat(),
        "acq_time": time_raw.zfill(4),
        "satellite": satellite,
        "instrument": instrument,
    })
    record = FirmsProvider.parse_csv_record(normalized, dataset_name=product)
    record["import_region"] = "Italy"
    record["raw_payload"] = json.dumps(row, default=str)
    identity = "|".join((
        product, satellite, acquired.isoformat(), time_raw.zfill(4),
        f"{latitude:.6f}", f"{longitude:.6f}",
    ))
    record["id"] = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return record


def _checkpoint_id(source_hash: str, product: str) -> str:
    return hashlib.sha256(f"{source_hash}:{product}".encode("utf-8")).hexdigest()


def _raw_detection_type(payload):
    for _ in range(3):
        if not payload:
            return None
        try:
            parsed = json.loads(payload)
        except (ValueError, TypeError):
            try:
                parsed = ast.literal_eval(payload)
            except (ValueError, SyntaxError, TypeError):
                return ("unparsed", str(payload))
        if not isinstance(parsed, dict):
            return ("unparsed", str(payload))
        if "type" in parsed:
            return str(parsed["type"]).strip()
        if "raw_payload" not in parsed:
            return None
        payload = parsed["raw_payload"]
    return ("unparsed", str(payload))


def _legacy_signature(record: dict, product: str) -> tuple:
    satellite = SATELLITES[product].get(str(record["satellite"]).upper(), record["satellite"])
    return (record["instrument"], satellite, str(record["acq_date"]), str(record["acq_time"]).zfill(4),
            round(record["latitude"], 6), round(record["longitude"], 6),
            record.get("version"), record.get("frp"), record.get("brightness"),
            record.get("bright_t31"), record.get("scan"), record.get("track"),
            record.get("daynight"), record.get("confidence_raw"), _raw_detection_type(record.get("raw_payload")))


async def _without_identical_legacy_rows(session, records: list[dict]) -> list[dict]:
    aliases = {
        "FIRMS_MODIS_C61": {"FIRMS_MODIS_NRT", "FIRMS_MODIS_SP"},
        "FIRMS_MODIS_ANNUAL": {"FIRMS_MODIS_NRT", "FIRMS_MODIS_SP"},
        "FIRMS_VIIRS_SNPP_375M": {"FIRMS_VIIRS_SNPP_NRT", "FIRMS_VIIRS_SNPP_SP"},
        "FIRMS_VIIRS_NOAA20_375M": {"FIRMS_VIIRS_NOAA20_NRT", "FIRMS_VIIRS_NOAA20_SP"},
        "FIRMS_VIIRS_NOAA21_375M": {"FIRMS_VIIRS_NOAA21_NRT", "FIRMS_VIIRS_NOAA21_SP"},
    }
    products = {r['dataset_name'] for r in records}
    legacy_names = set().union(*(aliases.get(p, set()) for p in products))
    legacy = (await session.scalars(select(FireDetection).where(
        FireDetection.dataset_name.in_(legacy_names), FireDetection.is_synthetic_demo != 'true',
        FireDetection.acq_date >= min(r['acq_date'] for r in records),
        FireDetection.acq_date <= max(r['acq_date'] for r in records),
    ))).all()
    signatures = {p: {_legacy_signature({c.name: getattr(row, c.name) for c in FireDetection.__table__.columns}, p)
                       for row in legacy if row.dataset_name in aliases.get(p, set())} for p in products}
    return [r for r in records if _legacy_signature(r, r['dataset_name']) not in signatures[r['dataset_name']]]


async def _insert_records(session, records: list[dict]) -> int:
    if not records:
        return 0
    records = await _without_identical_legacy_rows(session, records)
    if not records:
        return 0
    dialect = engine.dialect.name
    if dialect == "sqlite":
        statement = sqlite_insert(FireDetection).on_conflict_do_nothing(
            index_elements=["id"]
        )
    elif dialect == "postgresql":
        statement = pg_insert(FireDetection).on_conflict_do_nothing(
            index_elements=["id"]
        )
    else:
        existing_ids = set((await session.scalars(
            select(FireDetection.id).where(FireDetection.id.in_([r["id"] for r in records]))
        )).all())
        fresh = [record for record in records if record["id"] not in existing_ids]
        session.add_all(FireDetection(**record) for record in fresh)
        return len(fresh)
    connection = await session.connection()
    result = await connection.execute(statement.returning(FireDetection.id), records)
    return len(result.all())


async def import_archive(csv_path: Path, product: str, chunk_size: int = CHUNK_SIZE_DEFAULT) -> dict:
    if chunk_size < 1:
        raise ValueError("chunk_size must be greater than zero")
    digest = hashlib.sha256()
    with csv_path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    file_hash = digest.hexdigest()
    checkpoint_key = _checkpoint_id(file_hash, product)

    async with AsyncSessionLocal() as session:
        checkpoint = await session.get(FirmsImportCheckpoint, checkpoint_key)
        if checkpoint and checkpoint.status == "complete":
            return _checkpoint_summary(checkpoint, resumed=False, already_complete=True)
        if checkpoint is None:
            checkpoint = FirmsImportCheckpoint(
                id=checkpoint_key,
                source_file=str(csv_path.resolve()),
                file_sha256=file_hash,
                source_product=product,
                products_json=json.dumps([product]),
                status="running",
                coverage_status="observed_rows_only",
            )
            session.add(checkpoint)
            await session.commit()

        processed = checkpoint.processed_rows
        resumed = processed > 0
        totals = {
            "imported_count": checkpoint.imported_count,
            "invalid_count": checkpoint.invalid_count,
            "outside_count": checkpoint.outside_count,
            "duplicate_count": checkpoint.duplicate_count,
        }
        min_date, max_date = checkpoint.min_date, checkpoint.max_date
        chunk: list[dict] = []
        seen_ids: set[str] = set()

        with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(
                {name.strip().lower() for name in reader.fieldnames}
            ):
                raise ValueError(
                    "CSV header must include latitude, longitude, acq_date, acq_time, and satellite."
                )
            for _ in range(processed):
                next(reader, None)

            async def save_chunk(processed_in_chunk: int) -> None:
                nonlocal min_date, max_date, seen_ids
                imported_now = await _insert_records(session, chunk)
                totals["imported_count"] += imported_now
                totals["duplicate_count"] += len(chunk) - imported_now
                checkpoint.processed_rows += processed_in_chunk
                checkpoint.imported_count = totals["imported_count"]
                checkpoint.invalid_count = totals["invalid_count"]
                checkpoint.outside_count = totals["outside_count"]
                checkpoint.duplicate_count = totals["duplicate_count"]
                checkpoint.min_date = min_date
                checkpoint.max_date = max_date
                checkpoint.last_import_at = datetime.utcnow()
                await session.commit()
                chunk.clear()
                seen_ids.clear()

            rows_since_commit = 0
            for row in reader:
                if rows_since_commit >= chunk_size:
                    await save_chunk(rows_since_commit)
                    rows_since_commit = 0
                processed += 1
                rows_since_commit += 1
                try:
                    record = _normalized_record(row, product)
                except (InvalidArchiveRow, KeyError, TypeError, ValueError):
                    totals["invalid_count"] += 1
                    continue
                acquired = record["acq_date"]
                if not point_is_in_italy(record["latitude"], record["longitude"]):
                    totals["outside_count"] += 1
                    continue
                min_date = min(min_date, acquired) if min_date else acquired
                max_date = max(max_date, acquired) if max_date else acquired
                if record["id"] in seen_ids:
                    totals["duplicate_count"] += 1
                    continue
                seen_ids.add(record["id"])
                chunk.append(record)
                if rows_since_commit >= chunk_size:
                    await save_chunk(rows_since_commit)
                    rows_since_commit = 0
            if rows_since_commit or chunk:
                await save_chunk(rows_since_commit)

        checkpoint.status = "complete"
        checkpoint.coverage_status = "observed_rows_only"
        checkpoint.finished_at = datetime.utcnow()
        await session.commit()
        return _checkpoint_summary(checkpoint, resumed=resumed, already_complete=False)


def _checkpoint_summary(checkpoint, resumed: bool, already_complete: bool) -> dict:
    return {
        "source_file": checkpoint.source_file,
        "last_import_at": checkpoint.last_import_at.replace(tzinfo=timezone.utc).isoformat(),
        "status": checkpoint.status,
        "coverage_status": checkpoint.coverage_status,
        "processed_rows": checkpoint.processed_rows,
        "imported_count": checkpoint.imported_count,
        "invalid_count": checkpoint.invalid_count,
        "outside_count": checkpoint.outside_count,
        "duplicate_count": checkpoint.duplicate_count,
        "min_date": str(checkpoint.min_date) if checkpoint.min_date else None,
        "max_date": str(checkpoint.max_date) if checkpoint.max_date else None,
        "resumed": resumed,
        "already_complete": already_complete,
    }


async def update_recent(product: str, days: int) -> dict:
    if not settings.FIRMS_MAP_KEY.strip():
        raise RuntimeError("FIRMS_MAP_KEY is not configured; no recent data was requested.")
    if not 1 <= days <= min(settings.MAX_DOWNLOAD_DAYS_PER_REQUEST, FirmsProvider.MAX_AREA_API_DAYS):
        raise ValueError(
            f"Recent API windows must be between 1 and "
            f"{min(settings.MAX_DOWNLOAD_DAYS_PER_REQUEST, FirmsProvider.MAX_AREA_API_DAYS)} days."
        )
    details = PRODUCTS[product]
    source = details["recent_api_source"]
    if not source:
        raise ValueError(
            f"{product} is archive-import only; the configured recent Area API does not support it."
        )
    west, south, east, north = italy_geometry_bounds()
    records = await FirmsProvider.fetch_area_firms(
        west, south, east, north, source=source, day_range=days,
        start_date=date.today() - timedelta(days=days - 1), end_date=date.today(),
    )
    validated = []
    outside = invalid = duplicate = 0
    seen = set()
    for row in records:
        try:
            record = _normalized_record(row, product)
        except (InvalidArchiveRow, KeyError, TypeError, ValueError):
            invalid += 1
            continue
        if not point_is_in_italy(record["latitude"], record["longitude"]):
            outside += 1
            continue
        if record["id"] in seen:
            duplicate += 1
            continue
        seen.add(record["id"])
        validated.append(record)

    fetched_fingerprint = hashlib.sha256(
        json.dumps(
            [(record["id"], record["dataset_name"]) for record in validated],
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    checkpoint_key = _checkpoint_id(fetched_fingerprint, product)
    dates = [record["acq_date"] for record in validated]
    async with AsyncSessionLocal() as session:
        checkpoint = await session.get(FirmsImportCheckpoint, checkpoint_key)
        if checkpoint is None:
            checkpoint = FirmsImportCheckpoint(
                id=checkpoint_key,
                source_file=f"NASA FIRMS recent Area API ({source}, {days} days)",
                file_sha256=fetched_fingerprint,
                source_product=source,
                products_json=json.dumps([product]),
                status="running",
                coverage_status="observed_rows_only",
            )
            session.add(checkpoint)
        imported = await _insert_records(session, validated)
        checkpoint.status = "complete"
        checkpoint.processed_rows += len(records)
        checkpoint.imported_count += imported
        checkpoint.invalid_count += invalid
        checkpoint.outside_count += outside
        checkpoint.duplicate_count += duplicate + len(validated) - imported
        checkpoint.min_date = min(dates) if dates else checkpoint.min_date
        checkpoint.max_date = max(dates) if dates else checkpoint.max_date
        checkpoint.last_import_at = datetime.utcnow()
        checkpoint.finished_at = datetime.utcnow()
        await session.commit()
        return _checkpoint_summary(checkpoint, resumed=False, already_complete=False)


def italy_geometry_bounds() -> tuple[float, float, float, float]:
    from app.services.italy_coverage import italy_geometry
    return italy_geometry().bounds


async def main_async(args) -> dict:
    await init_db()
    if args.recent:
        product = product_id(args.product)
        return await update_recent(product, args.days)
    if not args.csv:
        raise ValueError("--csv is required unless --recent is used.")
    if not args.csv.is_file():
        raise ValueError(f"CSV file not found: {args.csv}")
    return await import_archive(args.csv, product_id(args.product), args.chunk_size)


async def execute_cli(args):
    try:
        result = await main_async(args)
        print(json.dumps(result, indent=2))
        return result
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--csv", type=Path, help="FIRMS historical archive CSV to import.")
    mode.add_argument("--recent", action="store_true", help="Fetch a supported recent Area API window.")
    parser.add_argument("--product", required=True, help="Product ID or FIRMS archive product, e.g. VIIRS_SNPP_SP.")
    parser.add_argument("--days", type=int, default=5, help="Recent API window, limited by backend settings (max 5).")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE_DEFAULT)
    args = parser.parse_args()
    asyncio.run(execute_cli(args))


if __name__ == "__main__":
    main()
