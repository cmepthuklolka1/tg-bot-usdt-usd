import asyncio
import json
import math
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from pydantic import ValidationError
from src.domain.models import ExchangeRateReport, RateSection, ExchangerOffer, P2PItem
from src.handlers.user import _format_amount_label
from src.services.antarctic import AntarcticTokenManager, _parse_rub_per_usdt_rate


class RenderReliabilityTests(unittest.TestCase):
    def test_unavailable_sources_are_explicit(self):
        text = ExchangeRateReport(cbrf_rate=None).format_for_telegram()
        self.assertNotIn("0.00", text)
        for name in ("ЦБ РФ", "Antarctic", "ABCEX", "UNISWAP"):
            self.assertIn(name, text)
        self.assertIn("недоступ", text)

    def test_large_report_has_complete_html_and_fits_telegram(self):
        sections = [RateSection(label=f"Source {i}", items=[(j, "82.51 ₽ " + "A" * 100) for j in range(100)]) for i in range(4)]
        text = ExchangeRateReport(cbrf_rate=80, sections=sections).format_for_telegram()
        self.assertLessEqual(len(text), 4000)
        self.assertEqual(text.count("<pre>"), text.count("</pre>"))
        self.assertIn("Source 3", text)
        self.assertIn("сокращ", text)

    def test_amount_label_does_not_round_away_rubles(self):
        self.assertEqual(_format_amount_label(150500), "150 500")
        self.assertEqual(_format_amount_label(100000), "100K")

    def test_models_reject_non_finite_and_negative_prices(self):
        for value in (float("nan"), float("inf"), -1, 0):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ExchangerOffer(exchanger_name="a", give_rub=80, get_usdt=1, rate=value)

    def test_antarctic_parser_rejects_invalid_numbers_and_shapes(self):
        for value in ("NaN", "Infinity", "-1", "0", {"amount": float("nan"), "scale": 2}, {"amount": 1, "scale": 100000}):
            with self.subTest(value=str(value)):
                self.assertIsNone(_parse_rub_per_usdt_rate({"data": {"rate": value}}))
        for data in ({"data": None}, {"data": []}, []):
            self.assertIsNone(_parse_rub_per_usdt_rate(data))


class TokenDurabilityTests(unittest.TestCase):
    def test_failed_save_preserves_previous_token_file(self):
        manager = AntarcticTokenManager()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tokens.json"
            original = '{"access_token":"old","refresh_token":"old"}'
            path.write_text(original)
            with patch("src.services.antarctic.config.antarctic_tokens_path", path), patch("src.utils.storage.json.dump", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    manager._save_tokens()
            self.assertEqual(path.read_text(), original)


if __name__ == "__main__":
    unittest.main()
