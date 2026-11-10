import csv
import math
import logging
import asyncio
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, timedelta
import httpx
from app.core.config import settings
from app.services.download_cache import DownloadCache

logger = logging.getLogger(__name__)

_download_slots = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)
_cache_locks: Dict[str, asyncio.Lock] = {}


class FirmsProviderError(Exception):
    def __init__(self, message: str, status_code: int = 502, retry_after: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class FirmsProvider:
    """
    NASA FIRMS (Fire Information for Resource Management System) Provider.
    Supports querying live NASA FIRMS API when MAP_KEY is provided,
    and parsing official FIRMS CSV exports.
    """

    BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api"
    MAX_AREA_API_DAYS = 5
    _cached_connectivity: Optional[Dict[str, Any]] = None
    _connectivity_checked_at: Optional[datetime] = None
    _last_successful_check: Optional[str] = None
    _last_successful_retrieval: Optional[str] = None
    _CONNECTIVITY_TTL_SECONDS: int = 300

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.FIRMS_MAP_KEY and settings.FIRMS_MAP_KEY.strip())

    @classmethod
    async def check_connectivity(cls, force: bool = False) -> Dict[str, Any]:
        """
        Validates connectivity with the official NASA FIRMS API via /api/data_availability/csv/{KEY}/ALL.
        Never returns or logs the secret MAP_KEY.
        Caches results for 300 seconds to prevent rate-limit exhaustion.
        """
        if not cls.is_configured():
            return {
                "configured": False,
                "connected": False,
                "status": "credentials_unconfigured",
                "message": "FIRMS_MAP_KEY is not configured in environment.",
                "available_products": [],
                "date_ranges": {},
                "last_check": cls._last_successful_check,
                "last_retrieval": cls._last_successful_retrieval,
            }

        now = datetime.utcnow()
        if (
            not force
            and cls._cached_connectivity is not None
            and cls._connectivity_checked_at is not None
            and (now - cls._connectivity_checked_at).total_seconds() < cls._CONNECTIVITY_TTL_SECONDS
        ):
            return cls._cached_connectivity

        url = f"{cls.BASE_URL}/data_availability/csv/{settings.FIRMS_MAP_KEY}/ALL"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                resp = await client.get(url, headers={"User-Agent": "AfterFire/1.0"})
                if resp.status_code == 200:
                    lines = resp.text.strip().splitlines()
                    date_ranges = {}
                    products = []
                    if len(lines) > 1:
                        reader = csv.DictReader(lines)
                        for r in reader:
                            pid = r.get("data_id", "").strip()
                            if pid:
                                products.append(pid)
                                date_ranges[pid] = {
                                    "min_date": r.get("min_date", "").strip(),
                                    "max_date": r.get("max_date", "").strip(),
                                }
                    if not date_ranges:
                        raise ValueError("NASA availability response did not contain recognized product/date rows.")
                    cls._last_successful_check = datetime.utcnow().isoformat() + "Z"
                    result = {
                        "configured": True,
                        "connected": True,
                        "status": "connected",
                        "message": f"NASA FIRMS API validated successfully. {len(products)} products available.",
                        "available_products": products,
                        "date_ranges": date_ranges,
                        "last_check": cls._last_successful_check,
                        "last_retrieval": cls._last_successful_retrieval,
                    }
                elif resp.status_code in (401, 403):
                    result = {
                        "configured": True,
                        "connected": False,
                        "status": "auth_failed",
                        "message": "NASA FIRMS rejected the MAP_KEY (authentication/authorization failure).",
                        "available_products": [],
                        "date_ranges": {},
                        "last_check": datetime.utcnow().isoformat() + "Z",
                        "last_retrieval": cls._last_successful_retrieval,
                    }
                else:
                    result = {
                        "configured": True,
                        "connected": False,
                        "status": "unavailable",
                        "message": f"NASA FIRMS responded with HTTP {resp.status_code}.",
                        "available_products": [],
                        "date_ranges": {},
                        "last_check": datetime.utcnow().isoformat() + "Z",
                        "last_retrieval": cls._last_successful_retrieval,
                    }
        except httpx.TimeoutException:
            result = {
                "configured": True,
                "connected": False,
                "status": "unavailable",
                "message": "Connection to NASA FIRMS API timed out.",
                "available_products": [],
                "date_ranges": {},
                "last_check": datetime.utcnow().isoformat() + "Z",
                "last_retrieval": cls._last_successful_retrieval,
            }
        except Exception as exc:
            result = {
                "configured": True,
                "connected": False,
                "status": "unavailable",
                "message": f"Could not reach NASA FIRMS ({type(exc).__name__}).",
                "available_products": [],
                "date_ranges": {},
                "last_check": datetime.utcnow().isoformat() + "Z",
                "last_retrieval": cls._last_successful_retrieval,
            }

        cls._cached_connectivity = result
        cls._connectivity_checked_at = now
        return result

    @classmethod
    def normalize_confidence(cls, instrument: str, raw_conf: Any) -> tuple[str, Optional[float]]:
        """
        Harmonizes confidence across MODIS and VIIRS:
        - MODIS gives 0-100% or ('l', 'n', 'h' in some NRT feeds)
        - VIIRS gives 'low', 'nominal', 'high' (or 'l', 'n', 'h')
        Returns: (confidence_level: 'low'|'nominal'|'high', confidence_pct: Optional[float])
        """
        if raw_conf is None:
            return "nominal", None
            
        str_val = str(raw_conf).strip().lower()
        
        # Check numeric 0-100 (typical MODIS)
        try:
            num = float(str_val)
            if num >= 80:
                return "high", num
            elif num >= 30:
                return "nominal", num
            else:
                return "low", num
        except ValueError:
            pass
            
        # Check categorical (typical VIIRS or NRT)
        if str_val in ("h", "high"):
            return "high", None
        elif str_val in ("n", "nominal", "med", "medium"):
            return "nominal", None
        elif str_val in ("l", "low"):
            return "low", None
        return "nominal", None

    @classmethod
    def parse_csv_record(cls, row: Dict[str, Any], dataset_name: str = "FIRMS_IMPORT") -> Dict[str, Any]:
        """
        Parses and standardizes a single row from a FIRMS CSV download or API response.
        Preserves original fields while creating normalized attributes.
        """
        instrument = row.get("instrument", "").strip().upper() or ("VIIRS" if "VIIRS" in dataset_name else "MODIS")
        satellite = row.get("satellite", "").strip() or "Unknown"
        
        lat = float(row.get("latitude", 0.0))
        lon = float(row.get("longitude", 0.0))
        
        acq_date_raw = str(row.get("acq_date", "")).strip()
        acq_time_raw = str(row.get("acq_time", "0000")).strip().zfill(4)
        
        try:
            parsed_date = datetime.strptime(acq_date_raw, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("Invalid FIRMS acquisition date; expected YYYY-MM-DD.") from exc
            
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Invalid FIRMS coordinates.")
        if not acq_time_raw.isdigit() or len(acq_time_raw) != 4 or int(acq_time_raw[:2]) > 23 or int(acq_time_raw[2:]) > 59:
            raise ValueError("Invalid FIRMS acquisition time.")
        raw_conf = row.get("confidence")
        conf_level, conf_pct = cls.normalize_confidence(instrument, raw_conf)
        
        # Extract brightness
        brightness = None
        for k in ("brightness", "bright_ti4"):
            if k in row and row[k] not in (None, ""):
                try:
                    brightness = float(row[k])
                    break
                except ValueError:
                    pass
                    
        bright_t31 = None
        for k in ("bright_t31", "bright_ti5"):
            if k in row and row[k] not in (None, ""):
                try:
                    bright_t31 = float(row[k])
                    break
                except ValueError:
                    pass
                    
        frp = None
        if "frp" in row and row["frp"] not in (None, ""):
            try:
                frp = float(row["frp"])
            except ValueError:
                pass
                
        scan = float(row["scan"]) if "scan" in row and row["scan"] else None
        track = float(row["track"]) if "track" in row and row["track"] else None
        daynight = str(row.get("daynight", "")).strip().upper() or None
        version = str(row.get("version", "")).strip() or None
        
        # Create unique deterministic ID if none provided
        rec_id = f"{instrument}_{satellite}_{acq_date_raw}_{acq_time_raw}_{lat:.4f}_{lon:.4f}"
        
        from app.services.italy_coverage import point_is_in_italy
        return {
            "import_region": "Italy" if point_is_in_italy(lat, lon) else "other",
            "id": rec_id,
            "latitude": lat,
            "longitude": lon,
            "acq_date": parsed_date,
            "acq_time": acq_time_raw,
            "satellite": satellite,
            "instrument": instrument,
            "confidence_raw": str(raw_conf) if raw_conf is not None else None,
            "confidence_level": conf_level,
            "confidence_pct": conf_pct,
            "frp": frp,
            "brightness": brightness,
            "bright_t31": bright_t31,
            "scan": scan,
            "track": track,
            "daynight": daynight,
            "dataset_name": dataset_name,
            "version": version,
            "raw_payload": str(row),
            "is_synthetic_demo": "false"
        }

    @classmethod
    async def fetch_area_firms(
        cls, 
        min_lon: float, 
        min_lat: float, 
        max_lon: float, 
        max_lat: float, 
        source: str = "VIIRS_SNPP_NRT", 
        day_range: Optional[int] = None,
        target_date: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        max_records: Optional[int] = None,
        response_byte_limit: Optional[int] = None,
        allow_partial: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Calls NASA FIRMS Area API:
        /api/area/csv/[MAP_KEY]/[SOURCE]/[EXTENT]/[DAY_RANGE]/[DATE]
        Extent format: west,south,east,north. DATE is the first date in each
        inclusive window; use the documented 1–5 day Area API windows.
        """
        if not cls.is_configured():
            raise FirmsProviderError("FIRMS_MAP_KEY is not configured; no live data was downloaded.", 503)

        cls._validate_bbox(min_lon, min_lat, max_lon, max_lat)
        if source not in {"MODIS_NRT", "MODIS_SP", "VIIRS_SNPP_NRT", "VIIRS_SNPP_SP",
                          "VIIRS_NOAA20_NRT", "VIIRS_NOAA20_SP", "VIIRS_NOAA21_NRT", "VIIRS_NOAA21_SP"}:
            raise FirmsProviderError(f"Unsupported FIRMS Area API source: {source}.", 400)

        if target_date:
            try:
                end_date = date.fromisoformat(target_date)
            except ValueError as exc:
                raise FirmsProviderError("target_date must use YYYY-MM-DD format.", 400) from exc
            start_date = end_date - timedelta(days=(day_range or 1) - 1)

        request_days = day_range or settings.MAX_DOWNLOAD_DAYS_PER_REQUEST
        if not 1 <= request_days <= min(settings.MAX_DOWNLOAD_DAYS_PER_REQUEST, cls.MAX_AREA_API_DAYS):
            raise FirmsProviderError(
                f"FIRMS request windows must contain 1-{min(settings.MAX_DOWNLOAD_DAYS_PER_REQUEST, cls.MAX_AREA_API_DAYS)} days.",
                400,
            )
        start_date = start_date or settings.ANALYSIS_START_DATE
        end_date = end_date or settings.ANALYSIS_END_DATE
        if start_date > end_date:
            raise FirmsProviderError("start_date must be on or before end_date.", 400)

        bbox = (min_lon, min_lat, max_lon, max_lat)
        windows = cls.split_date_range(start_date, end_date, request_days)
        total_downloaded = 0
        max_bytes = min(settings.MAX_DOWNLOAD_SIZE_MB * 1024 * 1024, response_byte_limit or settings.MAX_DOWNLOAD_SIZE_MB * 1024 * 1024)
        response_bytes = 0
        records: List[Dict[str, Any]] = []

        for window_start, window_end in windows:
            cache_key = {
                "provider": "NASA_FIRMS",
                "freshness_hour": datetime.utcnow().strftime("%Y%m%d%H") if window_end >= date.today() - timedelta(days=1) else None,
                "product": source,
                "bbox": [round(value, 6) for value in bbox],
                "start_date": window_start.isoformat(),
                "end_date": window_end.isoformat(),
            }
            csv_path, downloaded_bytes = await cls._get_window_csv(
                cache_key,
                bbox,
                source,
                window_start,
                window_end,
                max_bytes - total_downloaded,
            )
            total_downloaded += downloaded_bytes
            try:
                response_bytes += csv_path.stat().st_size
                if response_bytes > max_bytes:
                    raise FirmsProviderError('FIRMS response exceeds bounded body size; narrow the area or period.',413)
                with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
                    reader = csv.DictReader(stream)
                    required_fields = {"latitude", "longitude", "acq_date", "acq_time"}
                    if reader.fieldnames is None or not required_fields.issubset(reader.fieldnames):
                        raise FirmsProviderError(
                            "FIRMS returned an unrecognized CSV response for the requested region and dates."
                        )
                    for row in reader:
                        try:
                            parsed = cls.parse_csv_record(row, dataset_name=f"FIRMS_{source}")
                        except (ValueError, TypeError, AttributeError):
                            raise FirmsProviderError('NASA FIRMS returned invalid detection metadata; query incomplete.', 502) from None
                        if (
                            window_start <= parsed["acq_date"] <= window_end
                            and min_lon <= parsed["longitude"] <= max_lon
                            and min_lat <= parsed["latitude"] <= max_lat
                        ):
                            records.append(parsed)
                            if max_records is not None and len(records)>max_records:
                                if allow_partial:
                                    # One extra row signals truncation to the bounded map caller.
                                    return records
                                raise FirmsProviderError('FIRMS record limit reached; narrow the area or period.',413)
            finally:
                if not settings.DATA_CACHE_ENABLED:
                    csv_path.unlink(missing_ok=True)
        cls._last_successful_retrieval = datetime.utcnow().isoformat() + "Z"
        if cls._cached_connectivity:
            cls._cached_connectivity["last_retrieval"] = cls._last_successful_retrieval
        return records

    @classmethod
    def split_date_range(
        cls, start_date: date, end_date: date, max_days: int
    ) -> List[Tuple[date, date]]:
        if start_date > end_date:
            raise FirmsProviderError("start_date must be on or before end_date.", 400)
        if not 1 <= max_days <= cls.MAX_AREA_API_DAYS:
            raise FirmsProviderError("FIRMS Area API windows must be between 1 and 5 days.", 400)
        windows = []
        cursor = start_date
        while cursor <= end_date:
            window_end = min(cursor + timedelta(days=max_days - 1), end_date)
            windows.append((cursor, window_end))
            cursor = window_end + timedelta(days=1)
        return windows

    @staticmethod
    def _validate_bbox(west: float, south: float, east: float, north: float) -> None:
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            raise FirmsProviderError("Bounding box longitudes must be between -180 and 180.", 400)
        if not (-90 <= south <= 90 and -90 <= north <= 90):
            raise FirmsProviderError("Bounding box latitudes must be between -90 and 90.", 400)
        if west >= east or south >= north:
            raise FirmsProviderError("Bounding box must have west < east and south < north.", 400)
        if not settings.ALLOW_GLOBAL_DOWNLOADS and west == -180 and east == 180 and south == -90 and north == 90:
            raise FirmsProviderError("Global FIRMS downloads are disabled.", 403)

    @classmethod
    async def _get_window_csv(
        cls,
        cache_key: Dict[str, object],
        bbox: Tuple[float, float, float, float],
        source: str,
        start_date: date,
        end_date: date,
        remaining_bytes: int,
    ) -> Tuple[Path, int]:
        cache_path = DownloadCache.path_for(cache_key)
        if settings.DATA_CACHE_ENABLED:
            lock = _cache_locks.setdefault(str(cache_path), asyncio.Lock())
            async with lock:
                if cache_path.is_file():
                    return cache_path, 0
                return await cls._download_window(
                    cache_path, bbox, source, start_date, end_date, remaining_bytes, True
                )
        temp_path = settings.cache_dir / f"{uuid.uuid4().hex}.part"
        return await cls._download_window(
            temp_path, bbox, source, start_date, end_date, remaining_bytes, False
        )

    @classmethod
    async def _download_window(
        cls,
        destination: Path,
        bbox: Tuple[float, float, float, float],
        source: str,
        start_date: date,
        end_date: date,
        remaining_bytes: int,
        cache_result: bool,
    ) -> Tuple[Path, int]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.part")
        window_days = (end_date - start_date).days + 1
        extent = ",".join(f"{coordinate:.6f}" for coordinate in bbox)
        url = (
            f"{cls.BASE_URL}/area/csv/{settings.FIRMS_MAP_KEY}/{source}/"
            f"{extent}/{window_days}/{start_date.isoformat()}"
        )
        try:
            async with _download_slots:
                async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
                    for attempt in range(3):
                        try:
                            downloaded = 0
                            async with client.stream("GET", url) as response:
                                if response.status_code in {401, 403}:
                                    raise FirmsProviderError(
                                        "NASA FIRMS rejected the configured MAP_KEY (authentication/authorization failure).",
                                        502,
                                    )
                                if response.status_code == 429:
                                    retry = response.headers.get('Retry-After', '')
                                    wait = f' Retry after {retry} seconds.' if retry.isdigit() else ' Retry later.'
                                    raise FirmsProviderError('NASA FIRMS rate limit (HTTP 429).' + wait, 429, retry or None)
                                if response.status_code >= 500:
                                    if attempt < 2:
                                        retry_after = response.headers.get("Retry-After")
                                        delay = min(float(retry_after), 10.0) if retry_after and retry_after.isdigit() else 0.5 * (2 ** attempt)
                                        await asyncio.sleep(delay)
                                        continue
                                    raise FirmsProviderError(
                                        f"NASA FIRMS is temporarily unavailable (HTTP {response.status_code}).",
                                        503,
                                    )
                                if response.status_code != 200:
                                    raise FirmsProviderError(
                                        f"NASA FIRMS could not serve the requested product and period (HTTP {response.status_code}).",
                                        502,
                                    )
                                content_length = response.headers.get("Content-Length")
                                if content_length and int(content_length) > remaining_bytes:
                                    raise FirmsProviderError(
                                        f"Download size limit ({settings.MAX_DOWNLOAD_SIZE_MB} MB) reached for "
                                        f"{source} on {start_date} through {end_date}.",
                                        413,
                                    )
                                temp_path.parent.mkdir(parents=True, exist_ok=True)
                                with temp_path.open("wb") as stream:
                                    async for chunk in response.aiter_bytes():
                                        downloaded += len(chunk)
                                        if downloaded > remaining_bytes:
                                            raise FirmsProviderError(
                                                f"Download size limit ({settings.MAX_DOWNLOAD_SIZE_MB} MB) reached for "
                                                f"{source} on {start_date} through {end_date}.",
                                                413,
                                            )
                                        stream.write(chunk)
                            break
                        except httpx.TimeoutException as exc:
                            temp_path.unlink(missing_ok=True)
                            if attempt == 2:
                                raise FirmsProviderError(
                                    f"NASA FIRMS timed out for {source} on {start_date} through {end_date}.",
                                    504,
                                ) from exc
                            await asyncio.sleep(0.5 * (2 ** attempt))
                        except httpx.TransportError as exc:
                            temp_path.unlink(missing_ok=True)
                            if attempt == 2:
                                raise FirmsProviderError(
                                    "Could not connect to NASA FIRMS after three attempts.", 502
                                ) from exc
                            await asyncio.sleep(0.5 * (2 ** attempt))
            # FIRMS can return a text error with HTTP 200. Only cache observation CSVs.
            with temp_path.open('r', encoding='utf-8-sig', newline='') as stream:
                header = next(csv.reader(stream), [])
            if not {'latitude', 'longitude', 'acq_date', 'acq_time'}.issubset(header):
                raise FirmsProviderError('NASA FIRMS returned an unexpected response for this source and date range.')
            if cache_result:
                temp_path.replace(destination)
                return destination, downloaded
            return temp_path, downloaded
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
