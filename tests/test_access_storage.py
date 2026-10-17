import asyncio
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from src.handlers.access import AccessMiddleware
from src.utils.storage import WhitelistStorage, UserSettingsStorage


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_revoked_user_is_blocked_even_inside_fsm(self):
        middleware = AccessMiddleware(allowed=lambda uid: False)
        event = SimpleNamespace(from_user=SimpleNamespace(id=20), answer=AsyncMock())
        handler = AsyncMock()
        state = SimpleNamespace(clear=AsyncMock())
        await middleware(handler, event, {"state":state})
        handler.assert_not_awaited()
        state.clear.assert_awaited_once()


class StorageConcurrencyTests(unittest.TestCase):
    def test_threaded_read_modify_write_does_not_lose_users(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = WhitelistStorage(Path(tmp)/"users.json")
            with ThreadPoolExecutor(max_workers=10) as pool:
                list(pool.map(storage.add_user, range(50)))
            self.assertEqual(set(storage._read_data()["users"]), set(range(50)))

    def test_settings_defaults_are_copied_and_invalid_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = UserSettingsStorage(Path(tmp)/"settings.json")
            value = settings.get_exchange_settings(1, "bybit_1")
            value["max_amount"] = 1
            self.assertEqual(settings.get_exchange_settings(1, "bybit_1")["max_amount"], 100000)
            with self.assertRaises(ValueError):
                settings.set_exchange_settings(1, "bybit_1", "sequential", 999)

    def test_valid_json_with_wrong_structure_does_not_break_settings_or_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"store.json"
            for text in ('[]', '{"users":null}', '{"users":{"1":null}}'):
                path.write_text(text)
                self.assertEqual(UserSettingsStorage(path).get_exchange_settings(1, "bybit_1")["max_amount"],100000)
            path.write_text('{"users":null}')
            self.assertFalse(WhitelistStorage(path).is_allowed(99))
