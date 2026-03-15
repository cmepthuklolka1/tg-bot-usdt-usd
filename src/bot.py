import asyncio
import logging
from aiogram import Bot, Dispatcher

from src.config import config, init_whitelist
from src.handlers import user, admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Initializing whitelist storage...")
    init_whitelist()

    logger.info("Starting Telegram Bot...")
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()

    # Register routers (handlers)
    dp.include_router(user.router)
    dp.include_router(admin.router)

    try:
        # Drop pending updates and start polling
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Failed to start polling: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
