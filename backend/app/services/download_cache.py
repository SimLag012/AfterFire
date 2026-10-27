import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable

from app.core.config import settings


class DownloadCache:
    """Disk cache for disposable provider responses, separate from the application database."""

    @classmethod
    def path_for(cls, key: Dict[str, object]) -> Path:
        digest = hashlib.sha256(
            json.dumps(key, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return settings.cache_dir / f"{digest}.csv"

    @classmethod
    def inspect(cls) -> Dict[str, object]:
        files = cls._cache_files()
        return {
            "enabled": settings.DATA_CACHE_ENABLED,
            "directory": str(settings.cache_dir),
            "file_count": len(files),
            "size_bytes": sum(path.stat().st_size for path in files),
        }

    @classmethod
    def clear(cls) -> Dict[str, int]:
        files = cls._cache_files()
        removed = 0
        removed_bytes = 0
        for path in files:
            size = path.stat().st_size
            path.unlink()
            removed += 1
            removed_bytes += size
        return {"removed_files": removed, "removed_bytes": removed_bytes}

    @classmethod
    def _cache_files(cls) -> Iterable[Path]:
        if not settings.cache_dir.exists():
            return ()
        return (
            path for path in settings.cache_dir.iterdir()
            if path.is_file() and path.suffix == ".csv"
        )
