"""Bounded retry policy for transport interruptions and provider throttling."""
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx


def retry_after_seconds(value):
    if not value:
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        try:
            return max(0, math.ceil((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return 0


def retry_delay(exc, attempt):
    from app.providers.api_subsets import ProviderUnavailable
    if attempt >= 3:
        return None
    delay = 15 * 2 ** max(0, attempt - 1)
    if isinstance(exc, ProviderUnavailable):
        if exc.code in ('rate_limited', 'timeout', 'temporary_provider_error'):
            # Very long provider holds require manual retry; never shorten Retry-After.
            if exc.retry_after > 86400:
                return None
            return max(delay, 60 if exc.code == 'rate_limited' else 0, exc.retry_after)
    elif isinstance(exc, (httpx.TransportError, ConnectionError, TimeoutError)):
        return delay
    elif isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (408, 429, 500, 502, 503, 504):
        hold = retry_after_seconds(exc.response.headers.get('Retry-After'))
        return max(delay, hold) if hold <= 86400 else None
    return None
