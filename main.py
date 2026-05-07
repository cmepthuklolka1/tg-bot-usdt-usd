"""
Точка входа для запуска бота.
Использование: python main.py
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher

from src.config import config, init_whitelist, init_banned_sellers, init_user_settings
from src.handlers import user, admin
from src.utils.commands import set_bot_commands
from src.utils.storage import PinnedMessageStorage, WhitelistStorage
from src.handlers.user import generate_rates_report
from src.keyboards.menus import get_rates_keyboard
from src.services.antarctic import token_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def auto_update_task(bot: Bot):
    while True:
        await asyncio.sleep(3600)  # Ждём 1 час
        try:
            pinned_storage = PinnedMessageStorage()
            whitelist = WhitelistStorage()
            pinned_messages = pinned_storage.get_all()
            
            if not pinned_messages:
                continue
                
            logger.info("Запуск ежечасного автообновления курсов...")

            for str_chat_id, msg_id in pinned_messages.items():
                chat_id = int(str_chat_id)
                if not whitelist.is_allowed(chat_id):
                    continue

                # Персональный отчёт для каждого пользователя
                report_text = await generate_rates_report(user_id=chat_id)

                # Проверяем, реально ли сообщение закреплено в Telegram
                actual_pinned_id = None
                try:
                    chat_info = await bot.get_chat(chat_id)
                    if chat_info.pinned_message:
                        actual_pinned_id = chat_info.pinned_message.message_id
                except Exception:
                    pass

                if actual_pinned_id != msg_id:
                    logger.warning(f"Stored msg {msg_id} не закреплён в {chat_id} (pinned={actual_pinned_id}), пересоздаём")
                    pinned_storage.remove_pinned(chat_id)
                    try:
                        sent = await bot.send_message(
                            chat_id=chat_id,
                            text=report_text,
                            reply_markup=get_rates_keyboard(),
                            parse_mode="HTML",
                        )
                        try:
                            await bot.pin_chat_message(
                                chat_id=chat_id,
                                message_id=sent.message_id,
                                disable_notification=True,
                            )
                        except Exception:
                            pass
                        pinned_storage.set_pinned(chat_id, sent.message_id)
                    except Exception as e2:
                        logger.error(f"Не удалось восстановить сообщение для {chat_id}: {e2}")
                    continue

                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=report_text,
                        reply_markup=get_rates_keyboard(),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning(f"Не удалось обновить сообщение для {chat_id}: {e}")
                    pinned_storage.remove_pinned(chat_id)
                    try:
                        sent = await bot.send_message(
                            chat_id=chat_id,
                            text=report_text,
                            reply_markup=get_rates_keyboard(),
                            parse_mode="HTML",
                        )
                        try:
                            await bot.pin_chat_message(
                                chat_id=chat_id,
                                message_id=sent.message_id,
                                disable_notification=True,
                            )
                        except Exception:
                            pass
                        pinned_storage.set_pinned(chat_id, sent.message_id)
                    except Exception as e2:
                        logger.error(f"Не удалось восстановить сообщение для {chat_id}: {e2}")
                        pinned_storage.remove_pinned(chat_id)
            logger.info("Ежечасное автообновление завершено.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче auto_update_task: {e}")

async def main():
    logger.info("Инициализация файлов хранения...")
    init_whitelist()
    init_banned_sellers()
    init_user_settings()

    logger.info("Запуск Telegram-бота...")
    bot = Bot(token=config.bot_token)
    token_manager.set_bot(bot)
    dp = Dispatcher()

    # Регистрируем роутеры (обработчики)
    dp.include_router(user.router)
    dp.include_router(admin.router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        # Устанавливаем команды для интерфейса Telegram
        await set_bot_commands(bot)
        
        # Запуск фоновой задачи обновления
        bg_task = asyncio.create_task(auto_update_task(bot))
        
        logger.info("Бот запущен и ожидает сообщений...")
        await dp.start_polling(bot)
    finally:
        bg_task.cancel()
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
