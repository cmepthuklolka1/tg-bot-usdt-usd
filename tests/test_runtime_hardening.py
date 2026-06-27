import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

import main  # noqa: E402
import src.services.antarctic as antarctic_module  # noqa: E402
from src.domain.models import ExchangerOffer, P2PItem  # noqa: E402
from src.handlers.user import _format_bc_line, _format_bybit_line  # noqa: E402
from src.services.antarctic import AntarcticTokenManager, fetch_antarctic_onramp_rate  # noqa: E402
from src.utils.storage import WhitelistStorage  # noqa: E402
from scripts.test_antarctic_refresh import mask_token  # noqa: E402


class HtmlEscapingTests(unittest.TestCase):
    def test_external_names_are_escaped_before_telegram_html_rendering(self):
        bc_line = _format_bc_line(
            ExchangerOffer(
                exchanger_name="A&B <fast>",
                give_rub=100,
                get_usdt=1,
                rate=100,
            )
        )
        bybit_line = _format_bybit_line(
            P2PItem(
                id="1",
                nickName="Seller <b> & Co",
                price=100,
                quantity=10,
                minAmount=1000,
                maxAmount=10000,
                payments=["40"],
            )
        )

        self.assertIn("A&amp;B &lt;fast&gt;", bc_line)
        self.assertIn("Seller &lt;b&gt; &amp; Co", bybit_line)


class ConfigTests(unittest.TestCase):
    def test_importing_config_without_required_env_fails_fast(self):
        env = os.environ.copy()
        env.pop("BOT_TOKEN", None)
        env.pop("ADMIN_ID", None)
        env["PYTHONPATH"] = str(Path.cwd())

        result = subprocess.run(
            [sys.executable, "-c", "import src.config"],
            cwd=Path.cwd(),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BOT_TOKEN", result.stderr + result.stdout)


class MainLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_error_before_background_task_is_not_masked(self):
        class FakeSession:
            async def close(self):
                pass

        class FakeBot:
            session = FakeSession()

            def __init__(self, token):
                self.token = token

            async def delete_webhook(self, drop_pending_updates):
                raise RuntimeError("webhook failed")

        with patch.object(main, "Bot", FakeBot), \
             patch.object(main.token_manager, "set_bot"), \
             patch.object(main, "init_whitelist"), \
             patch.object(main, "init_banned_sellers"), \
             patch.object(main, "init_user_settings"):
            with self.assertRaisesRegex(RuntimeError, "webhook failed"):
                await main.main()


class StorageAtomicityTests(unittest.TestCase):
    def test_failed_write_does_not_corrupt_existing_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "whitelist.json"
            path.write_text(json.dumps({"users": [1]}), encoding="utf-8")
            storage = WhitelistStorage(path=path)

            with self.assertRaises(TypeError):
                storage._write_data({"users": {1}})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"users": [1]})


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text):
        self.messages.append((chat_id, text))


class AntarcticNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_token_file_notifies_admin_once(self):
        manager = AntarcticTokenManager()
        bot = FakeBot()
        manager.set_bot(bot)

        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = Path(tmpdir) / "missing_tokens.json"
            with patch("src.services.antarctic.config.antarctic_tokens_path", token_path), \
                 patch("src.services.antarctic.config.admin_id", 123):
                token = await manager.get_access_token()
                token_again = await manager.get_access_token()

        self.assertIsNone(token)
        self.assertIsNone(token_again)
        self.assertEqual(len(bot.messages), 1)
        self.assertEqual(bot.messages[0][0], 123)
        self.assertIn("Antarctic Wallet", bot.messages[0][1])

    async def test_topup_422_falls_back_to_general_buy_rate_and_notifies_admin(self):
        class FakeTokenManager:
            def __init__(self):
                self.messages = []

            async def get_access_token(self):
                return "access-token"

            async def force_refresh(self):
                return False

            async def _notify_admin(self, key, reason):
                self.messages.append((key, reason))

        class FakeResponse:
            def __init__(self, status_code, data, text=""):
                self.status_code = status_code
                self._data = data
                self.text = text

            def json(self):
                return self._data

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"HTTP Error {self.status_code}: {self.text}")

        class FakeSession:
            def __init__(self, *args, **kwargs):
                self.urls = []

            async def get(self, url, headers=None, timeout=None):
                self.urls.append(url)
                if "topup/rub/exchange_rate" in url:
                    return FakeResponse(422, {"status": "error"}, '{"error":"unprocessable"}')
                if "coins/rates" in url:
                    return FakeResponse(
                        200,
                        {
                            "status": "ok",
                            "data": {
                                "items": [
                                    {"coin": "BTC", "buyRate": "1000", "sellRate": "900"},
                                    {"coin": "USDT", "buyRate": "101.25", "sellRate": "99.75"},
                                ]
                            },
                        },
                    )
                raise AssertionError(f"Unexpected URL: {url}")

            async def close(self):
                pass

        fake_manager = FakeTokenManager()
        with patch.object(antarctic_module, "token_manager", fake_manager), \
             patch.object(antarctic_module, "AsyncSession", FakeSession):
            rate = await fetch_antarctic_onramp_rate()

        self.assertEqual(rate, 101.25)
        self.assertEqual(fake_manager.messages[0][0], "onramp_fallback")
        self.assertIn("422", fake_manager.messages[0][1])


class TokenScriptTests(unittest.TestCase):
    def test_refresh_token_is_masked_for_console_output(self):
        self.assertEqual(mask_token("1234567890abcdef"), "...90abcdef")
        self.assertEqual(mask_token("short"), "***")


if __name__ == "__main__":
    unittest.main()
