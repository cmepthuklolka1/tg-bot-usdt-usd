import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from src.services.cbrf import fetch_usd_rub_rate
from src.utils.http import HTTPFailure


DIRECT = "https://www.cbr.ru/scripts/XML_daily.asp"
MIRROR = "https://www.cbr-xml-daily.ru/daily_utf8.xml"
URLS = {DIRECT, MIRROR}
XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<ValCurs Date="17.10.2026" name="Foreign Currency Market">
<Valute ID="R01235"><NumCode>840</NumCode><CharCode>USD</CharCode>
<Nominal>1</Nominal><Name>US Dollar</Name><Value>83,6177</Value>
</Valute></ValCurs>'''


def response(content=XML):
    return SimpleNamespace(status_code=200, headers={}, content=content, infos={})


@asynccontextmanager
async def session(get):
    yield SimpleNamespace(get=get)


class CBRFRacingTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_valid_response_wins_and_cancels_slower_request(self):
        for fast in (DIRECT, MIRROR):
            with self.subTest(fast=fast):
                started = {url: asyncio.Event() for url in URLS}
                cancelled = set()

                async def get(url, **kwargs):
                    started[url].set()
                    try:
                        await asyncio.gather(*(event.wait() for event in started.values()))
                        if url == fast:
                            return response()
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        cancelled.add(url)
                        raise

                with patch("src.services.cbrf.shared_session", lambda: session(get)):
                    rate = await asyncio.wait_for(fetch_usd_rub_rate(), timeout=.3)
                self.assertEqual(rate.usd_rub, 83.6177)
                self.assertEqual(rate.date, datetime(2026, 10, 17))
                self.assertEqual(cancelled, URLS - {fast})

    async def test_invalid_fast_xml_never_beats_valid_response(self):
        invalid = [
            b"not XML",
            XML.replace(b' Date="17.10.2026"', b""),
            XML.replace(b"17.10.2026", b"not-a-date"),
            XML.replace(b"R01235", b"R01239"),
            XML.replace(b"83,6177", b"0"),
            XML.replace(b"83,6177", b"NaN"),
            XML.replace(b"<Nominal>1", b"<Nominal>0"),
            XML.replace(b"ValCurs", b"unexpected"),
        ]
        for content in invalid:
            with self.subTest(content=content):
                async def get(url, **kwargs):
                    if url == DIRECT:
                        return response(content)
                    await asyncio.sleep(0)
                    return response()

                with patch("src.services.cbrf.shared_session", lambda: session(get)):
                    rate = await asyncio.wait_for(fetch_usd_rub_rate(), timeout=.3)
                self.assertEqual(rate.usd_rub, 83.6177)
                self.assertEqual(rate.date, datetime(2026, 10, 17))

    async def test_nominal_is_applied_to_rate_per_one_usd(self):
        async def get(url, **kwargs):
            if url == DIRECT:
                return response(XML.replace(b"<Nominal>1", b"<Nominal>10")
                                .replace(b"83,6177", b"836,177"))
            await asyncio.Event().wait()

        with patch("src.services.cbrf.shared_session", lambda: session(get)):
            rate = await asyncio.wait_for(fetch_usd_rub_rate(), timeout=.3)
        self.assertAlmostEqual(rate.usd_rub, 83.6177)

    async def test_endpoint_retries_do_not_wait_for_other_failed_endpoint(self):
        mirror_attempts = 0

        async def get(url, **kwargs):
            nonlocal mirror_attempts
            if url == DIRECT:
                raise HTTPFailure(403)
            mirror_attempts += 1
            if mirror_attempts == 1:
                raise TimeoutError()
            return response()

        with patch("src.services.cbrf.shared_session", lambda: session(get)), \
                patch("src.utils.retry.random.uniform", return_value=0):
            rate = await asyncio.wait_for(fetch_usd_rub_rate(), timeout=.3)
        self.assertEqual(rate.usd_rub, 83.6177)

    async def test_both_invalid_endpoints_raise_instead_of_returning_fake_rate(self):
        async def get(url, **kwargs):
            return response(b"invalid XML")

        with patch("src.services.cbrf.shared_session", lambda: session(get)):
            with self.assertRaises(ValueError):
                await fetch_usd_rub_rate()

    async def test_parent_cancellation_drains_both_requests(self):
        started = {url: asyncio.Event() for url in URLS}
        ended = set()

        async def get(url, **kwargs):
            started[url].set()
            try:
                await asyncio.Event().wait()
            finally:
                ended.add(url)

        with patch("src.services.cbrf.shared_session", lambda: session(get)):
            task = asyncio.create_task(fetch_usd_rub_rate())
            try:
                await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started.values())), timeout=.3)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertEqual(ended, URLS)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
