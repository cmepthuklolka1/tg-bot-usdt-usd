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

    async def _pin_report(self, bot, chat_id, message_id, previous_id):
        await bot.pin_chat_message(chat_id=chat_id, message_id=message_id, disable_notification=True)
        self.storage.set_pinned(chat_id, message_id)
        self._pending.pop(chat_id, None)
        if previous_id and previous_id != message_id:
            try:
                await bot.unpin_chat_message(chat_id=chat_id, message_id=previous_id)
            except Exception as error:
                # The new report is already visible, pinned and persisted.
                logger.warning("source=telegram event=previous_pin_cleanup_deferred error_kind=%s", type(error).__name__)

    async def update(self, bot, chat_id, text, *, verify_pin=False, message_id=None):
        async with self._locks.setdefault(chat_id, asyncio.Lock()):
            if time.monotonic() < self._retry_at.get(chat_id, 0):
                return False
            try:
                previous_id = self.storage.get_all().get(str(chat_id))
                target_id = message_id if message_id is not None else previous_id
                if target_id:
                    try:
                        await bot.edit_message_text(chat_id=chat_id, message_id=target_id, text=text,
                                                    reply_markup=get_rates_keyboard(), parse_mode="HTML")
                    except TelegramBadRequest as error:
                        reason = error.message.lower()
                        if "message to edit not found" in reason:
                            target_id = None
                        elif "message is not modified" not in reason:
                            raise
                    if target_id:
                        if target_id != previous_id:
                            self._pending[chat_id] = target_id
                            await self._pin_report(bot, chat_id, target_id, previous_id)
                        elif verify_pin:
                            # Unknown pin state is never treated as a missing message.
                            chat = await bot.get_chat(chat_id)
                            actual = getattr(getattr(chat, "pinned_message", None), "message_id", None)
                            if actual != target_id:
                                await bot.pin_chat_message(chat_id=chat_id, message_id=target_id, disable_notification=True)
                        return True
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
                await self._pin_report(bot, chat_id, pending_id, previous_id)
                return True
            except TelegramRetryAfter as error:
                self._retry_at[chat_id] = time.monotonic() + error.retry_after
                logger.warning("source=telegram error_kind=rate_limited retry_after=%s", error.retry_after)
            except Exception as error:
                logger.warning("source=telegram error_kind=%s", type(error).__name__)
            return False


publisher = ReportPublisher()
