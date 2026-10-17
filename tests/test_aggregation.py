import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from src.services.reports import RateCollector


class CollectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "cache.json"
        self.collector = RateCollector(self.path, ttl=30)

    async def test_concurrent_calls_share_request_and_cancelled_waiter_does_not_cancel_it(self):
        gate = asyncio.Event()
        async def work():
            await gate.wait()
            return 80.0
        fetch = AsyncMock(side_effect=work)
        first = asyncio.create_task(self.collector.get("uniswap", fetch))
        second = asyncio.create_task(self.collector.get("uniswap", fetch))
        await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        gate.set()
        self.assertEqual((await second).value, 80)
        self.assertEqual(fetch.await_count, 1)
        self.assertEqual((await self.collector.get("uniswap", fetch)).value, 80)

    async def test_failed_source_uses_last_good_timestamp_and_survives_restart(self):
        value = await self.collector.get("uniswap", AsyncMock(return_value=80))
        other = RateCollector(self.path, ttl=0)
        stale = await other.get("uniswap", AsyncMock(side_effect=TimeoutError()))
        self.assertEqual(stale.value, 80)
        self.assertEqual(stale.fetched_at, value.fetched_at)
        self.assertEqual(stale.status, "stale")

    async def test_expired_stale_data_is_not_shown_as_current(self):
        await self.collector.get("uniswap", AsyncMock(return_value=80))
        self.collector.last_good["uniswap"].fetched_at = 0
        result = await self.collector.get("uniswap", AsyncMock(side_effect=TimeoutError()), force=True)
        self.assertIsNone(result.value)
        self.assertEqual(result.status, "unavailable")

    async def test_source_deadline_does_not_block_other_sources(self):
        async def hangs():
            await asyncio.Event().wait()
        self.collector.timeout = .01
        bad, good = await asyncio.gather(self.collector.get("bad", hangs), self.collector.get("uniswap", AsyncMock(return_value=80)))
        self.assertEqual(good.value, 80)
        self.assertEqual(bad.error_kind, "network_timeout")
