"""HTTP sessions live for the event loop; diagnostics never include bodies/tokens."""

import asyncio
import math
import logging
import time
from contextlib import asynccontextmanager
from email.utils import parsedate_to_datetime
from weakref import WeakKeyDictionary

from curl_cffi.requests import AsyncSession
from curl_cffi import CurlInfo
from curl_cffi.requests.exceptions import ConnectionError, Timeout, HTTPError

from ..config import config

_sessions = WeakKeyDictionary()
logger = logging.getLogger(__name__)


class HTTPFailure(Exception):
    def __init__(self, status: int, retry_after: float | None = None):
        self.status = status
        self.retry_after = retry_after
        super().__init__(f"HTTP {status}")


def retry_after_seconds(value, *, now=None):
    if not value:
        return None
    try:
        delay = float(value)
    except (TypeError, ValueError):
        try:
            delay = parsedate_to_datetime(value).timestamp() - (time.time() if now is None else now)
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0.0, delay) if math.isfinite(delay) else None


def check_response(response):
    timings = getattr(response, "infos", {})
    if timings:
        logger.info("source=http http_status=%s dns_ms=%.1f connect_ms=%.1f tls_ms=%.1f total_ms=%.1f", response.status_code,
                    timings.get(CurlInfo.NAMELOOKUP_TIME, 0)*1000, timings.get(CurlInfo.CONNECT_TIME, 0)*1000,
                    timings.get(CurlInfo.APPCONNECT_TIME, 0)*1000, timings.get(CurlInfo.TOTAL_TIME, 0)*1000)
    if response.status_code >= 400:
        raise HTTPFailure(response.status_code, retry_after_seconds(getattr(response, "headers", {}).get("Retry-After")))
    return response


def classify_error(error) -> str:
    status = getattr(error, "status", None)
    if status is None and isinstance(error, HTTPError):
        status = getattr(getattr(error, "response", None), "status_code", None)
    if status == 401:
        return "auth_rejected"
    if status == 403:
        return "access_denied"
    if status == 429:
        return "rate_limited"
    if status == 408 or isinstance(error, (TimeoutError, Timeout)):
        return "network_timeout"
    if status and status >= 500:
        return "upstream_error"
    if isinstance(error, (ConnectionError, OSError)):
        return "network_error"
    return "invalid_response"


def get_session(namespace="public", *, factory=AsyncSession):
    loop = asyncio.get_running_loop()
    sessions = _sessions.setdefault(loop, {})
    if namespace not in sessions:
        sessions[namespace] = factory(impersonate="chrome110", max_clients=config.max_http_clients,
                                      curl_infos=[CurlInfo.NAMELOOKUP_TIME, CurlInfo.CONNECT_TIME, CurlInfo.APPCONNECT_TIME, CurlInfo.TOTAL_TIME])
    return sessions[namespace]


@asynccontextmanager
async def shared_session(namespace="public"):
    yield get_session(namespace)


async def close_sessions():
    sessions = _sessions.pop(asyncio.get_running_loop(), {})
    await asyncio.gather(*(s.close() for s in sessions.values()), return_exceptions=True)


def request_timeout():
    return (min(config.connect_timeout, config.fetch_timeout), config.fetch_timeout)
