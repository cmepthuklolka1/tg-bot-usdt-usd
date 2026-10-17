import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from src.handlers.user import cb_show_rates
from src.services.publishing import ReportPublisher
from src.utils.storage import PinnedMessageStorage


class RatesNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_show_rates_opens_report_in_clicked_menu_instead_of_only_editing_old_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = PinnedMessageStorage(Path(tmp) / "pins.json")
            storage.set_pinned(1, 42)
            publisher = ReportPublisher(storage)
            messages = {42: "old report", 100: "main menu"}

            async def edit(*, chat_id, message_id, text, **kwargs):
                messages[message_id] = text

            bot = SimpleNamespace(edit_message_text=edit,
                                  pin_chat_message=AsyncMock(), unpin_chat_message=AsyncMock(),
                                  send_message=AsyncMock())
            callback = SimpleNamespace(data="show_rates", from_user=SimpleNamespace(id=1),
                                       message=SimpleNamespace(chat=SimpleNamespace(id=1), message_id=100),
                                       bot=bot, answer=AsyncMock())
            with patch("src.services.publishing.publisher", publisher), \
                    patch("src.handlers.user.generate_rates_report", AsyncMock(return_value="current report")):
                await cb_show_rates(callback)

            self.assertEqual(messages[100], "current report")
            self.assertEqual(storage.get_all(), {"1": 100})
            bot.unpin_chat_message.assert_awaited_once_with(chat_id=1, message_id=42)
            bot.send_message.assert_not_awaited()

    async def test_failed_publication_gives_visible_feedback(self):
        callback = SimpleNamespace(data="show_rates", from_user=SimpleNamespace(id=1),
                                   message=SimpleNamespace(chat=SimpleNamespace(id=1), message_id=100,
                                                           answer=AsyncMock()),
                                   bot=SimpleNamespace(), answer=AsyncMock())
        with patch("src.services.publishing.publisher.update", AsyncMock(return_value=False)), \
                patch("src.handlers.user.generate_rates_report", AsyncMock(return_value="report")):
            await cb_show_rates(callback)
        callback.message.answer.assert_awaited_once()
        self.assertIn("Попробуйте", callback.message.answer.call_args.args[0])
