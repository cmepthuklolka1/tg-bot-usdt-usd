"""Access is checked on every update, including ongoing FSM conversations."""

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from ..config import config
from ..utils.storage import WhitelistStorage


class AccessMiddleware(BaseMiddleware):
    def __init__(self, *, admin_only=False, allowed=None):
        self.admin_only = admin_only
        self.allowed = allowed or WhitelistStorage().is_allowed

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        allowed = user is not None and (user.id == config.admin_id if self.admin_only else self.allowed(user.id))
        if not allowed:
            if data.get("state"):
                await data["state"].clear()
            if isinstance(event, CallbackQuery):
                await event.answer("Нет доступа.", show_alert=True)
            elif hasattr(event, "answer"):
                await event.answer("🔒 Доступ ограничен.")
            return
        # A private bot must not expose a whitelisted user's report in a group.
        message = event.message if isinstance(event, CallbackQuery) else event
        if getattr(getattr(message, "chat", None), "type", "private") != "private":
            if isinstance(event, CallbackQuery):
                await event.answer("Откройте личный чат с ботом.", show_alert=True)
            return
        if self.admin_only and isinstance(event, Message) and event.text is None:
            await event.answer("Отправьте текстовое сообщение с ID или именем продавца.")
            return
        return await handler(event, data)
