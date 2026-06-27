import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from src.keyboards.menus import (  # noqa: E402
    get_settings_bc_coin_keyboard,
    get_settings_bc_payment_keyboard,
    get_settings_bybit_amount_keyboard,
)
from src.utils.storage import WhitelistStorage  # noqa: E402


def _callback_data(markup):
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    ]


class WhitelistStorageTests(unittest.TestCase):
    def test_remove_user_returns_true_when_user_was_removed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "whitelist.json"
            path.write_text('{"users": [1, 2]}', encoding="utf-8")
            storage = WhitelistStorage(path=path)

            removed = storage.remove_user(2)

            self.assertTrue(removed)
            self.assertEqual(storage._read_data(), {"users": [1]})


class KeyboardCallbackTests(unittest.TestCase):
    def test_settings_back_buttons_use_registered_settings_menu_callback(self):
        markups = [
            get_settings_bc_payment_keyboard(),
            get_settings_bc_coin_keyboard(),
            get_settings_bybit_amount_keyboard(),
        ]

        all_callbacks = [
            callback
            for markup in markups
            for callback in _callback_data(markup)
        ]

        self.assertNotIn("settings_bestchange", all_callbacks)
        self.assertNotIn("settings_bybit", all_callbacks)
        self.assertEqual(all_callbacks.count("settings_menu"), 3)


if __name__ == "__main__":
    unittest.main()
