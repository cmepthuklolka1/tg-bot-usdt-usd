import asyncio
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from src.handlers.access import AccessMiddleware
from src.handlers.user import delete_pin_notification
from src.utils.storage import WhitelistStorage, UserSettingsStorage
from aiogram.types import CallbackQuery, Message


class AccessTests(unittest.IsolatedAsyncioTestCase):
    def pin_event(self, *, chat_id=1, chat_type="private"):
        return Message.model_validate({
            "message_id": 100, "date": 1700000000,
            "chat": {"id": chat_id, "type": chat_type},
            "from": {"id": 99, "is_bot": True, "first_name": "Rate bot"},
            "pinned_message": {"message_id": 42, "date": 0,
                               "chat": {"id": chat_id, "type": chat_type}},
        })

    async def test_bot_pin_notification_is_deleted_without_false_access_denial(self):
        middleware = AccessMiddleware(allowed=lambda uid: uid == 1)
        state = SimpleNamespace(clear=AsyncMock())

        async def handler(event, data):
            await delete_pin_notification(event)

        with patch.object(Message, "answer", new_callable=AsyncMock) as answer, \
                patch.object(Message, "delete", new_callable=AsyncMock) as delete:
            await middleware(handler, self.pin_event(), {"state": state})
        delete.assert_awaited_once()
        answer.assert_not_awaited()
        state.clear.assert_not_awaited()

    async def test_pin_notification_in_unauthorized_chat_is_silently_ignored(self):
        middleware = AccessMiddleware(allowed=lambda uid: uid == 1)
        handler = AsyncMock()
        state = SimpleNamespace(clear=AsyncMock())
        with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
            await middleware(handler, self.pin_event(chat_id=2), {"state": state})
        handler.assert_not_awaited()
        answer.assert_not_awaited()
        state.clear.assert_not_awaited()

    async def test_group_pin_notification_never_reaches_private_bot_handler(self):
        middleware = AccessMiddleware(allowed=lambda uid: True)
        handler = AsyncMock()
        with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
            await middleware(handler, self.pin_event(chat_id=-1, chat_type="group"), {})
        handler.assert_not_awaited()
        answer.assert_not_awaited()

    async def test_real_unauthorized_message_still_receives_access_denial(self):
        middleware = AccessMiddleware(allowed=lambda uid: False)
        event = Message.model_validate({"message_id": 100, "date": 1700000000,
                                       "chat": {"id": 2, "type": "private"},
                                       "from": {"id": 2, "is_bot": False, "first_name": "User"},
                                       "text": "/start"})
        handler = AsyncMock()
        with patch.object(Message, "answer", new_callable=AsyncMock) as answer:
            await middleware(handler, event, {})
        handler.assert_not_awaited()
        answer.assert_awaited_once()

    async def test_unauthorized_callback_still_receives_alert(self):
        middleware = AccessMiddleware(allowed=lambda uid: False)
        event = CallbackQuery.model_validate({"id": "test-query", "chat_instance": "test-chat",
                                             "from": {"id": 2, "is_bot": False, "first_name": "User"},
                                             "data": "show_rates"})
        handler = AsyncMock()
        with patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer:
            await middleware(handler, event, {})
        handler.assert_not_awaited()
        answer.assert_awaited_once_with("Нет доступа.", show_alert=True)

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
