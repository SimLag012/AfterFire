"""Cross-process cache locks: flock on Unix, native shared locks on Windows."""
import os

if os.name != "nt":
    from fcntl import LOCK_EX, LOCK_NB, LOCK_SH, LOCK_UN, flock
else:
    import errno
    import portalocker

    LOCK_EX = portalocker.LOCK_EX
    LOCK_NB = portalocker.LOCK_NB
    LOCK_SH = portalocker.LOCK_SH
    LOCK_UN = portalocker.LOCK_UN

    def flock(handle, operation):
        if operation == LOCK_UN:
            portalocker.unlock(handle)
            return
        try:
            portalocker.lock(handle, operation)
        except portalocker.exceptions.AlreadyLocked as exc:
            # Existing callers treat lock contention as retryable, not failure.
            raise BlockingIOError(errno.EWOULDBLOCK, "File is locked") from exc
