import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from src.utils.retry import DEFAULT_RETRY
from src.utils.http import HTTPFailure, classify_error, retry_after_seconds


class HTTPPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_errors_are_not_retried(self):
        operation = AsyncMock(side_effect=ValueError("bad schema"))
        with self.assertRaises(ValueError):
            await DEFAULT_RETRY(operation)()
        self.assertEqual(operation.await_count, 1)

    async def test_timeout_is_retried_and_401_is_not(self):
        operation = AsyncMock(side_effect=[TimeoutError(), 82])
        with patch("src.utils.retry.asyncio.sleep", AsyncMock()):
            self.assertEqual(await DEFAULT_RETRY(operation)(), 82)
        operation = AsyncMock(side_effect=HTTPFailure(401))
        with self.assertRaises(HTTPFailure):
            await DEFAULT_RETRY(operation)()
        self.assertEqual(operation.await_count, 1)

    async def test_cancellation_is_not_retried(self):
        operation = AsyncMock(side_effect=asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await DEFAULT_RETRY(operation)()
        self.assertEqual(operation.await_count, 1)

    def test_status_and_timeout_classification(self):
        self.assertEqual(classify_error(TimeoutError()), "network_timeout")
        self.assertEqual(classify_error(HTTPFailure(401)), "auth_rejected")
        self.assertEqual(classify_error(HTTPFailure(429)), "rate_limited")
        self.assertEqual(classify_error(HTTPFailure(503)), "upstream_error")
        self.assertEqual(classify_error(ValueError()), "invalid_response")

    def test_retry_after_is_bounded_and_parses_http_date(self):
        self.assertEqual(retry_after_seconds("120"), 120)
        self.assertIsNone(retry_after_seconds("NaN"))
        self.assertEqual(retry_after_seconds("Wed, 21 Oct 2015 07:28:00 GMT", now=1445412470), 10)
