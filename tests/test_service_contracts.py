import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from src.domain.models import P2PItem
from src.services.bybit_p2p import filter_bybit_offers
from src.services.bestchange import parse_bestchange_html


class ServiceContractTests(unittest.TestCase):
    def test_bybit_amount_must_fit_limits_and_available_volume(self):
        def offer(name, minimum=1000, maximum=100000, quantity=1000):
            return P2PItem(id=name, nickName=name, price=80, quantity=quantity, minAmount=minimum, maxAmount=maximum, payments=["40"])
        items = [offer("ok"), offer("too_big_min", minimum=60000), offer("too_small_max", maximum=40000), offer("no_volume", quantity=100), offer("banned")]
        self.assertEqual([x.nickName for x in filter_bybit_offers(items, 50000, {"BANNED"})], ["ok"])

    def test_bestchange_fixture_skips_zero_and_invalid_rows_before_dedup(self):
        html = '''<table id="content_table"><tbody>
        <tr><td></td><td><div class="bj"><a>A&amp;B</a></div></td><td>80 RUB</td><td>0 USDT</td></tr>
        <tr><td></td><td><div class="bj"><a>A&amp;B</a></div></td><td>81 RUB</td><td>1 USDT</td></tr>
        <tr><td></td><td><div class="bj"><a>C</a></div></td><td>NaN RUB</td><td>1 USDT</td></tr>
        </tbody></table>'''
        offers = parse_bestchange_html(html).offers
        self.assertEqual([(x.exchanger_name, x.rate) for x in offers], [("A&B", 81)])

    def test_bestchange_schema_drift_does_not_look_like_empty_market(self):
        with self.assertRaises(ValueError):
            parse_bestchange_html('<table id="content_table"><tbody><tr><td></td><td>Seller</td><td>new-format</td><td>1 USDT</td></tr></tbody></table>')
        with self.assertRaises(ValueError):
            parse_bestchange_html('<table id="content_table"><tbody><tr class="odd"><td><div class="bj"><a>Seller</a></div></td><td>81 RUB</td><td>1 USDT</td></tr></tbody></table>')
