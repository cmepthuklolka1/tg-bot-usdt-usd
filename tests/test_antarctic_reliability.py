import asyncio
import base64
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from src.services import antarctic as aw


def jwt(exp=None):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp or int(time.time())+172800}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def response(status=200, data=None):
    return SimpleNamespace(status_code=status, headers={}, json=lambda: data)


class TokenTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/"tokens.json"
        self.path.write_text(json.dumps({"access_token": jwt(), "refresh_token": "original"}))
        self.patcher = patch.object(aw.config, "antarctic_tokens_path", self.path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.manager = aw.AntarcticTokenManager()

    async def test_manual_file_replacement_is_loaded_and_bad_replacement_preserves_state(self):
        original = await self.manager.get_access_token()
        replacement = jwt(int(time.time())+200000)
        self.path.write_text(json.dumps({"access_token": replacement, "refresh_token": "replacement"}))
        self.assertEqual(await self.manager.get_access_token(), replacement)
        self.path.write_text('{"access_token":')
        self.assertEqual(await self.manager.get_access_token(), replacement)
        self.assertEqual(self.manager._refresh_token, "replacement")

    async def test_failed_save_keeps_rotated_pair_and_retries_persistence(self):
        await self.manager.get_access_token()
        rotated = jwt(int(time.time())+300000)
        session = SimpleNamespace(post=AsyncMock(return_value=response(200, {"status":"ok", "data":{"accessToken":rotated,"refreshToken":"rotated","expiredAt":int(time.time())+300000}})))
        with patch.object(aw, "_session", return_value=session), patch.object(self.manager, "_save_tokens", side_effect=OSError("disk full")):
            self.assertTrue(await self.manager.force_refresh())
        self.assertEqual(self.manager._access_token, rotated)
        self.assertEqual(self.manager.error_kind, "storage_error")
        self.assertEqual(await self.manager.get_access_token(), rotated)
        self.assertEqual(json.loads(self.path.read_text())["refresh_token"], "rotated")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    async def test_concurrent_401_refreshes_only_once(self):
        old = await self.manager.get_access_token()
        rotated = jwt(int(time.time())+300000)
        async def refresh():
            await asyncio.sleep(0)
            self.manager._access_token = rotated
            return True
        operation = AsyncMock(side_effect=refresh)
        with patch.object(self.manager, "_do_refresh", operation):
            self.assertEqual(await asyncio.gather(self.manager.force_refresh(old), self.manager.force_refresh(old)), [True, True])
        self.assertEqual(operation.await_count, 1)

    async def test_network_refresh_failure_does_not_become_auth_rejection(self):
        self.path.write_text(json.dumps({"access_token": jwt(int(time.time())-10), "refresh_token":"original"}))
        session = SimpleNamespace(post=AsyncMock(side_effect=TimeoutError()))
        with patch.object(aw, "_session", return_value=session):
            self.assertIsNone(await self.manager.get_access_token())
        self.assertEqual(self.manager.error_kind, "network_timeout")

    async def test_refresh_401_is_auth_rejection_and_bad_pair_is_not_saved(self):
        await self.manager.get_access_token()
        old = self.path.read_text()
        session = SimpleNamespace(post=AsyncMock(return_value=response(401)))
        with patch.object(aw, "_session", return_value=session):
            self.assertFalse(await self.manager.force_refresh())
        self.assertEqual(self.manager.error_kind, "auth_rejected")
        session.post.return_value = response(200, {"status":"ok", "data":{"accessToken": "bad", "refreshToken":"", "expiredAt":"x"}})
        self.manager._next_refresh = 0
        with patch.object(aw, "_session", return_value=session):
            self.assertFalse(await self.manager.force_refresh())
        self.assertEqual(self.path.read_text(), old)

    async def test_manual_pair_replaced_during_refresh_is_not_overwritten(self):
        await self.manager.get_access_token()
        manual = jwt(int(time.time())+400000)
        async def post(*args, **kwargs):
            self.path.write_text(json.dumps({"access_token": manual, "refresh_token":"manual"}))
            return response(200,{"status":"ok", "data":{"accessToken":jwt(int(time.time())+300000),"refreshToken":"rotated-old","expiredAt":int(time.time())+300000}})
        with patch.object(aw, "_session", return_value=SimpleNamespace(post=post)):
            self.assertTrue(await self.manager.force_refresh())
        self.assertEqual(self.manager._access_token, manual)
        self.assertEqual(json.loads(self.path.read_text())["refresh_token"], "manual")

    async def test_cancelled_waiter_does_not_cancel_or_lose_refresh_rotation(self):
        await self.manager.get_access_token()
        started, gate = asyncio.Event(), asyncio.Event()
        async def post(*args, **kwargs):
            started.set()
            await gate.wait()
            return response(200,{"status":"ok", "data":{"accessToken":jwt(int(time.time())+300000),"refreshToken":"rotated","expiredAt":int(time.time())+300000}})
        with patch.object(aw, "_session", return_value=SimpleNamespace(post=post)):
            waiter = asyncio.create_task(self.manager.force_refresh())
            await started.wait()
            waiter.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiter
            gate.set()
            await self.manager.close()
        self.assertEqual(json.loads(self.path.read_text())["refresh_token"], "rotated")


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_access_401_after_accepted_refresh_does_not_request_relogin(self):
        session = SimpleNamespace(get=AsyncMock(return_value=response(401)))
        manager = SimpleNamespace(get_access_token=AsyncMock(return_value="new-token"), error_kind=None, force_refresh=AsyncMock(return_value=True))
        with patch.object(aw, "_session", return_value=session), patch.object(aw, "token_manager", manager):
            quote = await aw.fetch_antarctic_quote()
        self.assertEqual(quote.error_kind, "access_denied")
        self.assertEqual(manager.force_refresh.await_count, 1)

    async def test_timeout_and_bad_json_still_try_other_endpoints(self):
        session = SimpleNamespace(get=AsyncMock(side_effect=[TimeoutError(), response(200, {"status":"ok","data":{"rate":"82.51"}})]))
        manager = SimpleNamespace(get_access_token=AsyncMock(return_value="token"), error_kind=None, force_refresh=AsyncMock())
        with patch.object(aw, "_session", return_value=session), patch.object(aw, "token_manager", manager), patch.object(aw.config, "fetch_retries", 1):
            quote = await aw.fetch_antarctic_quote()
        self.assertEqual(quote.rate, 82.51)
        self.assertEqual(quote.source, "Antarctic SBP")
        self.assertTrue(quote.degraded)
        self.assertEqual(session.get.await_count, 2)

    async def test_disabled_cash_and_working_sbp_are_healthy(self):
        session = SimpleNamespace(get=AsyncMock(side_effect=[response(422, {"errors":{"base":["FEATURE_DISABLED"]}}), response(200,{"status":"ok","data":{"rate":{"amount":8251,"scale":2}}})]))
        manager = SimpleNamespace(get_access_token=AsyncMock(return_value="token"), error_kind=None)
        with patch.object(aw, "_session", return_value=session), patch.object(aw, "token_manager", manager):
            quote = await aw.fetch_antarctic_quote()
        self.assertFalse(quote.degraded)
        self.assertEqual(quote.rate, 82.51)
