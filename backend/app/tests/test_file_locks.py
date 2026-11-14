"""Exercise actual OS locks across independent Python processes."""
import subprocess
import sys

import pytest
from app.core import file_locks as locks

CHILD = """
import sys
from app.core import file_locks as locks
with open(sys.argv[1], "a") as handle:
    try:
        locks.flock(handle, getattr(locks, sys.argv[2]) | locks.LOCK_NB)
    except BlockingIOError:
        print("blocked")
    else:
        print("acquired")
        locks.flock(handle, locks.LOCK_UN)
"""


def probe(path, kind):
    result = subprocess.run(
        [sys.executable, "-c", CHILD, str(path), kind],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return result.stdout.strip()


@pytest.mark.parametrize("held,requested,expected", [
    ("LOCK_SH", "LOCK_SH", "acquired"),
    ("LOCK_SH", "LOCK_EX", "blocked"),
    ("LOCK_EX", "LOCK_SH", "blocked"),
    ("LOCK_EX", "LOCK_EX", "blocked"),
])
def test_cross_process_lock_and_release(tmp_path, held, requested, expected):
    path = tmp_path / "cache.lock"
    with path.open("a") as handle:
        locks.flock(handle, getattr(locks, held))
        try:
            assert probe(path, requested) == expected
        finally:
            locks.flock(handle, locks.LOCK_UN)
        assert probe(path, "LOCK_EX") == "acquired"
