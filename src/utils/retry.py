"""Retry temporary failures only, inside a single elapsed-time budget."""

import asyncio
import functools
import logging
import random
import time

from ..config import config
from .http import classify_error

logger = logging.getLogger(__name__)
TRANSIENT = {"network_timeout", "network_error", "rate_limited", "upstream_error"}


def DEFAULT_RETRY(function):
    @functools.wraps(function)
    async def wrapped(*args, **kwargs):
        deadline = time.monotonic() + config.source_timeout
        for attempt in range(1, config.fetch_retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Source request deadline exceeded")
            try:
                return await asyncio.wait_for(function(*args, **kwargs), timeout=remaining)
            except Exception as error:
                kind = classify_error(error)
                if kind not in TRANSIENT or attempt == config.fetch_retries:
                    raise
                retry_after = getattr(error, "retry_after", None)
                delay = max(random.uniform(.3, min(4, 2 ** attempt)), retry_after or 0)
                if delay >= deadline - time.monotonic():
                    raise
                logger.warning("source=%s error_kind=%s attempt=%s retry_delay=%.2f", function.__name__, kind, attempt, delay)
                await asyncio.sleep(delay)
    return wrapped


CBRF_RETRY = DEFAULT_RETRY
