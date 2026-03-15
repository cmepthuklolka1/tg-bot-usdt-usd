import logging
from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat

from ..config import config
from ..utils.storage import WhitelistStorage

logger = logging.getLogger(__name__)

async def set_bot_commands(bot: Bot):
    admin_cmds = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="add_user", description="➕ Выдать доступ"),
        BotCommand(command="remove_user", description="⛔ Забрать доступ"),
        BotCommand(command="ban_seller", description="🚫 В ЧС (Bybit)"),
        BotCommand(command="unban_seller", description="✅ Из ЧС (Bybit)"),
        BotCommand(command="cancel", description="❌ Отменить действие")
    ]
    user_cmds = [
        BotCommand(command="start", description="Главное меню")
    ]
    
    try:
        await bot.delete_my_commands()
        
        # Admin scope
        await bot.set_my_commands(commands=admin_cmds, scope=BotCommandScopeChat(chat_id=config.admin_id))
        
        # User scopes
        storage = WhitelistStorage()
        users = storage._read_data().get("users", [])
        for u_id in users:
            if u_id != config.admin_id:
                try:
                    await bot.set_my_commands(commands=user_cmds, scope=BotCommandScopeChat(chat_id=u_id))
                except Exception:
                    pass
        logger.info("Команды бота успешно установлены.")
    except Exception as e:
        logger.error(f"Ошибка при установке команд бота: {e}")
