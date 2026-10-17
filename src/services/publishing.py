"""One publisher owns pin state; transient Telegram errors never delete it."""

import asyncio
import logging
import time

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from ..keyboards.menus import get_rates_keyboard
from ..utils.storage import PinnedMessageStorage

logger = logging.getLogger(__name__)


class ReportPublisher:
    def __init__(self, storage=None):
        self.storage = storage or PinnedMessageStorage()
        self._locks = {}
        self._retry_at = {}
        self._pending = {}

    async def update(self, bot, chat_id, text, *, verify_pin=False):
        async with self._locks.setdefault(chat_id, asyncio.Lock()):
            if time.monotonic() < self._retry_at.get(chat_id, 0):
                return False
            try:
                message_id = self.storage.get_all().get(str(chat_id))
                if message_id:
                    try:
                        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text,
                                                    reply_markup=get_rates_keyboard(), parse_mode="HTML")
                        if verify_pin:
                            # Unknown pin state is never treated as a missing message.
                            chat = await bot.get_chat(chat_id)
                            actual = getattr(getattr(chat, "pinned_message", None), "message_id", None)
                            if actual != message_id:
                                await bot.pin_chat_message(chat_id=chat_id, message_id=message_id, disable_notification=True)
                        return True
                    except TelegramBadRequest as error:
                        reason = error.message.lower()
                        if "message is not modified" in reason:
                            if verify_pin:
                                chat = await bot.get_chat(chat_id)
                                if getattr(getattr(chat, "pinned_message", None), "message_id", None) != message_id:
                                    await bot.pin_chat_message(chat_id=chat_id, message_id=message_id, disable_notification=True)
                            return True
                        if "message to edit not found" not in reason:
                            raise
                # Retain an unpinned draft after a transient pin failure. A later
                # attempt pins this message rather than sending another duplicate.
                pending_id = self._pending.get(chat_id)
                if pending_id is None:
                    sent = await bot.send_message(chat_id=chat_id, text=text,
                                                  reply_markup=get_rates_keyboard(), parse_mode="HTML")
                    pending_id = sent.message_id
                    self._pending[chat_id] = pending_id
                else:
                    try:
                        await bot.edit_message_text(chat_id=chat_id, message_id=pending_id, text=text,
                                                   reply_markup=get_rates_keyboard(), parse_mode="HTML")
                    except TelegramBadRequest as error:
                        if "message to edit not found" in error.message.lower():
                            self._pending.pop(chat_id, None)
                        if "message is not modified" not in error.message.lower():
                            raise
                await bot.pin_chat_message(chat_id=chat_id, message_id=pending_id, disable_notification=True)
                self.storage.set_pinned(chat_id, pending_id)
                self._pending.pop(chat_id, None)
                return True
            except TelegramRetryAfter as error:
                self._retry_at[chat_id] = time.monotonic() + error.retry_after
                logger.warning("source=telegram error_kind=rate_limited retry_after=%s", error.retry_after)
            except Exception as error:
                logger.warning("source=telegram error_kind=%s", type(error).__name__)
            return False


publisher = ReportPublisher()
