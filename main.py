"""Telegram rate monitor with supervised background work and shared snapshots."""

import asyncio
import logging
import os
import subprocess
import time
from pathlib import Path

from aiogram import Bot, Dispatcher

from src.config import BASE_DIR, config, init_whitelist, init_banned_sellers, init_user_settings
from src.handlers import user, admin
from src.handlers.user import generate_rates_report
from src.services.antarctic import token_manager
from src.services.incidents import monitor
from src.services.publishing import publisher
from src.services.reports import collector, recovery_task
from src.services.antarctic import fetch_antarctic_quote
from src.services.cbrf import fetch_usd_rub_rate
from src.utils.commands import set_bot_commands
from src.utils.http import close_sessions
from src.utils.storage import PinnedMessageStorage, WhitelistStorage, _write_json_atomic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def release_version():
    try:
        stamp = BASE_DIR / ".release-sha"
        if stamp.exists():
            return stamp.read_text().strip()[:64]
        return subprocess.check_output(["git", "-C", str(BASE_DIR), "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def write_health():
    _write_json_atomic(config.runtime_state_path.with_name("health.json"), {
        "pid": os.getpid(), "checked_at": time.time(), "version": release_version(),
        "last_success": {key: value.fetched_at for key, value in collector.last_good.items()},
        "antarctic_recovering": monitor.needs_recovery("antarctic"),
    })


async def update_all_reports(bot):
    whitelist = WhitelistStorage()
    for chat, message_id in PinnedMessageStorage().get_all().items():
        try:
            chat_id = int(chat)
            if not whitelist.is_allowed(chat_id):
                continue
            text = await generate_rates_report(chat_id)
            await publisher.update(bot, chat_id, text, verify_pin=True)
        except Exception as error:
            logger.warning("source=background_report error_kind=%s", type(error).__name__)


async def auto_update_task(bot):
    loop = asyncio.get_running_loop()
    next_run = loop.time()
    while True:
        try:
            await update_all_reports(bot)
            logger.info("event=background_update_completed")
        except Exception as error:
            logger.warning("source=background_update error_kind=%s", type(error).__name__)
        next_run += config.update_interval
        while next_run <= loop.time():
            next_run += config.update_interval
        await asyncio.sleep(max(0, next_run-loop.time()))


async def heartbeat_task():
    while True:
        try:
            write_health()
        except OSError:
            logger.error("source=health error_kind=storage_error")
        await asyncio.sleep(30)


async def warm_sources():
    await asyncio.gather(collector.get("cbrf", fetch_usd_rub_rate), collector.get("antarctic", fetch_antarctic_quote))


async def main():
    init_whitelist()
    init_banned_sellers()
    init_user_settings()
    logger.info("event=starting version=%s", release_version())
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()
    dp.include_router(user.router)
    dp.include_router(admin.router)
    tasks = []
    async def notify(text):
        await bot.send_message(config.admin_id, text)
    monitor.sender = notify
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await set_bot_commands(bot)
        await bot.get_me()
        tasks = [asyncio.create_task(auto_update_task(bot)), asyncio.create_task(recovery_task()),
                 asyncio.create_task(heartbeat_task()), asyncio.create_task(warm_sources()),
                 asyncio.create_task(dp.start_polling(bot))]
        # Polling handles SIGTERM by returning normally. It owns process lifetime;
        # a stopped infinite worker also triggers cleanup instead of silent loss.
        watched = [tasks[0], tasks[1], tasks[2], tasks[4]]
        done, _ = await asyncio.wait(watched, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        if tasks[4] not in done:
            raise RuntimeError("A background worker stopped unexpectedly")
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await collector.close()
        await token_manager.close()
        await close_sessions()
        await bot.session.close()
        monitor.sender = None
        logger.info("event=stopped")


if __name__ == "__main__":
    asyncio.run(main())
