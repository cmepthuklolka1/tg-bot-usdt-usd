import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.methods import EditMessageText
from src.services.publishing import ReportPublisher
from src.utils.storage import PinnedMessageStorage


class PublisherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.storage = PinnedMessageStorage(Path(self.tmp.name)/"pins.json")
        self.storage.set_pinned(1, 42)
        self.publisher = ReportPublisher(self.storage)
        self.bot = SimpleNamespace(get_chat=AsyncMock(), edit_message_text=AsyncMock(), send_message=AsyncMock(return_value=SimpleNamespace(message_id=43)), pin_chat_message=AsyncMock(), delete_message=AsyncMock())

    async def test_transient_edit_failure_keeps_pin_and_does_not_send(self):
        self.bot.edit_message_text.side_effect = TimeoutError()
        self.assertFalse(await self.publisher.update(self.bot, 1, "report"))
        self.assertEqual(self.storage.get_all(), {"1":42})
        self.bot.send_message.assert_not_awaited()

    async def test_rate_limit_does_not_create_new_message(self):
        self.bot.edit_message_text.side_effect = TelegramRetryAfter(EditMessageText(text="x"), "limited", 10)
        self.assertFalse(await self.publisher.update(self.bot, 1, "report"))
        self.bot.send_message.assert_not_awaited()
        self.assertEqual(self.storage.get_all(), {"1":42})

    async def test_missing_message_is_recreated_and_pin_failure_keeps_old_mapping(self):
        self.bot.edit_message_text.side_effect = TelegramBadRequest(EditMessageText(text="x"), "message to edit not found")
        self.bot.pin_chat_message.side_effect = TimeoutError()
        self.assertFalse(await self.publisher.update(self.bot, 1, "report"))
        self.assertEqual(self.storage.get_all(), {"1":42})
        self.bot.delete_message.assert_not_awaited()

    async def test_valid_message_is_edited_without_checking_pin(self):
        self.assertTrue(await self.publisher.update(self.bot, 1, "report"))
        self.bot.get_chat.assert_not_awaited()
        self.bot.send_message.assert_not_awaited()

    async def test_concurrent_show_creates_at_most_one_message(self):
        self.storage.remove_pinned(1)
        await asyncio.gather(*(self.publisher.update(self.bot, 1, "report") for _ in range(3)))
        self.bot.send_message.assert_awaited_once()
        self.assertEqual(self.storage.get_all(), {"1":43})

    async def test_invalid_html_does_not_destroy_mapping(self):
        self.bot.edit_message_text.side_effect = TelegramBadRequest(EditMessageText(text="x"), "can't parse entities")
        self.assertFalse(await self.publisher.update(self.bot, 1, "bad html"))
        self.bot.send_message.assert_not_awaited()

    async def test_failed_pin_retries_same_draft_even_if_text_is_unchanged(self):
        self.storage.remove_pinned(1)
        self.bot.pin_chat_message.side_effect = [TimeoutError(), None]
        self.assertFalse(await self.publisher.update(self.bot, 1, "report"))
        self.bot.edit_message_text.side_effect = TelegramBadRequest(EditMessageText(text="x"), "message is not modified")
        self.assertTrue(await self.publisher.update(self.bot, 1, "report"))
        self.bot.send_message.assert_awaited_once()

    async def test_get_chat_failure_is_not_evidence_of_missing_pin(self):
        self.bot.get_chat.side_effect = TimeoutError()
        self.assertFalse(await self.publisher.update(self.bot, 1, "report", verify_pin=True))
        self.assertEqual(self.storage.get_all(), {"1":42})
        self.bot.send_message.assert_not_awaited()

    async def test_unchanged_report_still_repins_confirmed_missing_pin(self):
        self.bot.edit_message_text.side_effect = TelegramBadRequest(EditMessageText(text="x"), "message is not modified")
        self.bot.get_chat.return_value = SimpleNamespace(pinned_message=None)
        self.assertTrue(await self.publisher.update(self.bot, 1, "report", verify_pin=True))
        self.bot.pin_chat_message.assert_awaited_once_with(chat_id=1, message_id=42, disable_notification=True)
