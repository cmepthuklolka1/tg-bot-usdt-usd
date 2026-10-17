import asyncio
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

import main
from src.services import reports


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_polling_shutdown_cancels_workers_and_closes_resources(self):
        stopped = []
        async def worker(*args):
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(True)
        bot = Mock()
        bot.delete_webhook = AsyncMock()
        bot.get_me = AsyncMock()
        bot.session.close = AsyncMock()
        dispatcher = Mock()
        dispatcher.start_polling = AsyncMock(return_value=None)
        with patch.object(main, "Bot", return_value=bot), patch.object(main, "Dispatcher", return_value=dispatcher), patch.object(main, "init_whitelist"), patch.object(main, "init_banned_sellers"), patch.object(main, "init_user_settings"), patch.object(main, "set_bot_commands", AsyncMock()), patch.object(main, "auto_update_task", worker), patch.object(main, "recovery_task", worker), patch.object(main, "heartbeat_task", worker), patch.object(main, "warm_sources", AsyncMock()), patch.object(main.collector, "close", AsyncMock()), patch.object(main.token_manager, "close", AsyncMock()):
            await asyncio.wait_for(main.main(), timeout=.1)
        self.assertEqual(len(stopped), 3)
        bot.session.close.assert_awaited_once()

    async def test_startup_warms_sources_without_any_pinned_chats(self):
        fetch = AsyncMock()
        with patch.object(main.collector, "get", fetch):
            await main.warm_sources()
        self.assertEqual({call.args[0] for call in fetch.call_args_list}, {"cbrf", "antarctic"})

    async def test_failed_user_does_not_abort_updates_for_others(self):
        pins = Mock()
        pins.get_all.return_value = {"1":42, "2":43}
        whitelist = Mock()
        whitelist.is_allowed.return_value = True
        publish = AsyncMock(return_value=True)
        build = AsyncMock(side_effect=[ValueError("bad user settings"), "ok"])
        with patch.object(main, "PinnedMessageStorage", return_value=pins), patch.object(main, "WhitelistStorage", return_value=whitelist), patch.object(main, "generate_rates_report", build), patch.object(main.publisher, "update", publish):
            await main.update_all_reports(Mock())
        publish.assert_awaited_once()
        self.assertEqual(publish.call_args.args[1], 2)

    async def test_recovery_loop_polls_failed_source_without_user_request(self):
        observed = []
        async def sleep(_):
            if observed:
                raise asyncio.CancelledError()
        async def get(*args, **kwargs):
            observed.append((args, kwargs))
        with patch.object(reports.asyncio, "sleep", sleep), patch.object(reports.monitor, "needs_recovery", return_value=True), patch.object(reports.collector, "get", get):
            with self.assertRaises(asyncio.CancelledError):
                await reports.recovery_task()
        self.assertTrue(observed[0][1]["force"])
