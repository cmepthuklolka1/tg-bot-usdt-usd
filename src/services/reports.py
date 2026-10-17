"""Shared source snapshots and per-user reports, with explicit data freshness."""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from pydantic import TypeAdapter

from ..config import config
from ..domain.models import CBRFRate, BestChangeRates, P2PItem, PositivePrice, ExchangeRateReport, RateSection
from ..utils.http import classify_error
from ..utils.storage import UserSettingsStorage, DISPLAY_DEFAULTS, _write_json_atomic
from .abcex import fetch_abcex_prices
from .antarctic import AntarcticQuote, fetch_antarctic_quote, token_manager
from .bestchange import fetch_bestchange_rates
from .bybit_p2p import fetch_bybit_offers, filter_bybit_offers
from .cbrf import fetch_usd_rub_rate
from .incidents import monitor
from .uniswap import fetch_owb_usdc_price

logger = logging.getLogger(__name__)


@dataclass
class SourceResult:
    value: object = None
    fetched_at: float = 0
    status: str = "unavailable"
    error_kind: str | None = None

    def note(self):
        if self.status == "stale":
            age = max(0, int(time.time()-self.fetched_at))
            return f"последний успех {age // 60} мин {age % 60} сек назад; обновление не удалось"
        return ""


def _decode(key, value):
    if key == "cbrf":
        return CBRFRate.model_validate(value)
    if key.startswith("bestchange:"):
        return BestChangeRates.model_validate(value)
    if key == "bybit":
        return TypeAdapter(list[P2PItem]).validate_python(value)
    if key == "abcex":
        return TypeAdapter(tuple[PositivePrice, PositivePrice]).validate_python(value)
    if key == "uniswap":
        return TypeAdapter(PositivePrice).validate_python(value)
    if key == "antarctic":
        value = dict(value)
        value["rate"] = TypeAdapter(PositivePrice).validate_python(value["rate"])
        return AntarcticQuote(**value)
    raise ValueError("Unknown source")


def _encode(value):
    if isinstance(value, AntarcticQuote):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_encode(item) for item in value]
    return value


class SourceUnavailable(Exception):
    def __init__(self, kind):
        self.kind = kind
        super().__init__(kind)


class RateCollector:
    def __init__(self, path, *, ttl=None):
        self.path = Path(path)
        self.ttl = config.cache_ttl if ttl is None else ttl
        self.timeout = config.source_timeout
        self.last_good = {}
        self.cache = {}
        self.tasks = {}
        self._semaphore = asyncio.Semaphore(config.max_http_clients)
        try:
            saved = json.loads(self.path.read_text())
            for key, item in saved.items():
                try:
                    stamp = float(item["fetched_at"])
                    if not 0 < stamp <= time.time()+60:
                        continue
                    self.last_good[key] = SourceResult(_decode(key, item["value"]), stamp, "ok")
                except (ValueError, TypeError, KeyError):
                    continue
        except (OSError, ValueError, AttributeError):
            pass

    def _save(self):
        try:
            _write_json_atomic(self.path, {key: {"value": _encode(item.value), "fetched_at": item.fetched_at} for key, item in self.last_good.items()}, ensure_ascii=False)
        except (OSError, TypeError, ValueError):
            logger.warning("source=rate_cache error_kind=storage_error")

    async def get(self, key, factory, *, force=False):
        cached = self.cache.get(key)
        if not force and cached and time.monotonic() - cached[0] < self.ttl:
            return cached[1]
        if key not in self.tasks:
            task = asyncio.create_task(self._fetch(key, factory))
            self.tasks[key] = task
            def finished(completed):
                if self.tasks.get(key) is completed:
                    self.tasks.pop(key, None)
            task.add_done_callback(finished)
        return await asyncio.shield(self.tasks[key])

    async def _fetch(self, key, factory):
        started = time.monotonic()
        try:
            async def run():
                async with self._semaphore:
                    return await factory()
            value = await asyncio.wait_for(run(), timeout=self.timeout)
            if value is None:
                raise SourceUnavailable("invalid_response")
            if isinstance(value, AntarcticQuote) and value.rate is None:
                raise SourceUnavailable(value.error_kind or "invalid_response")
            value = _decode(key, _encode(value))
            result = SourceResult(value, time.time(), "ok")
            self.last_good[key] = result
            self._save()
        except Exception as error:
            kind = error.kind if isinstance(error, SourceUnavailable) else classify_error(error)
            good = self.last_good.get(key)
            result = replace(good, status="stale", error_kind=kind) if good and time.time()-good.fetched_at <= config.max_stale_seconds else SourceResult(error_kind=kind)
            logger.warning("source=%s error_kind=%s duration_ms=%d", key, kind, (time.monotonic()-started)*1000)
        self.cache[key] = (time.monotonic(), result)
        if key == "antarctic":
            if result.error_kind:
                await monitor.failure("antarctic", result.error_kind)
            elif result.value.degraded:
                await monitor.failure("antarctic", "degraded")
            else:
                await monitor.success("antarctic")
            if token_manager.error_kind:
                await monitor.failure("antarctic_tokens", token_manager.error_kind)
            else:
                await monitor.success("antarctic_tokens")
        return result

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


collector = RateCollector(config.runtime_state_path.with_name("rate_cache.json"))
settings_storage = UserSettingsStorage()


def _format_amount_label(amount):
    if amount >= 1000000 and amount % 1000000 == 0:
        return f"{amount // 1000000}M"
    if amount % 1000 == 0:
        return f"{amount // 1000}K"
    return f"{amount:,}".replace(",", " ")


def _format_bc_line(offer):
    return f"{offer.rate:>6.2f} ₽  {escape(offer.exchanger_name[:55])}"


def _format_bybit_line(item):
    return f"{item.price:>6.2f} ₽  {escape(item.nickName[:55])}"


def _apply_display_settings(items, settings, formatter):
    value = settings.get("value", 5)
    if settings.get("mode") == "positions":
        return [(pos, formatter(items[pos-1])) for pos in sorted(value) if 0 < pos <= len(items)]
    return [(i+1, formatter(item)) for i, item in enumerate(items[:value])]


async def generate_rates_report(user_id=None):
    settings = settings_storage.get_all_settings(user_id) if user_id else DISPLAY_DEFAULTS
    jobs = {"cbrf": fetch_usd_rub_rate, "abcex": fetch_abcex_prices, "antarctic": fetch_antarctic_quote,
            "uniswap": fetch_owb_usdc_price, "bybit": fetch_bybit_offers}
    for key in ("bestchange_1", "bestchange_2"):
        s = settings[key]
        payment, coin = s.get("payment", "sberbank"), s.get("coin", "tether-bep20")
        jobs[f"bestchange:{payment}:{coin}"] = lambda payment=payment, coin=coin: fetch_bestchange_rates(payment=payment, coin=coin)
    async def collect(key, factory):
        try:
            return await asyncio.wait_for(collector.get(key, factory), timeout=config.report_timeout)
        except TimeoutError:
            return SourceResult(error_kind="network_timeout")
    values = await asyncio.gather(*(collect(key, factory) for key, factory in jobs.items()))
    results = dict(zip(jobs, values))
    cbr, abcex, antarctic, owb = [results[key].value for key in ("cbrf", "abcex", "antarctic", "uniswap")]
    sections = []
    payments = {"sberbank":"Сбер", "vtb":"ВТБ", "tinkoff":"Т-Банк", "alfaclick":"Альфа-Банк"}
    for key in ("bestchange_1", "bestchange_2", "bybit_1", "bybit_2"):
        s = settings[key]
        if key.startswith("bestchange"):
            payment, coin = s.get("payment", "sberbank"), s.get("coin", "tether-bep20")
            result = results[f"bestchange:{payment}:{coin}"]
            items = result.value.offers if result.value else []
            label = f"BestChange ({payments.get(payment, payment)} → {coin.upper()})"
            formatter = _format_bc_line
        else:
            result = results["bybit"]
            amount = s.get("max_amount", 100000)
            items = filter_bybit_offers(result.value or [], amount)
            label = f"Bybit P2P (USDT/RUB) [{_format_amount_label(amount)} ₽]"
            formatter = _format_bybit_line
        if result.status == "unavailable":
            label += " — временно недоступен"
        elif result.status == "stale":
            label += " — " + result.note()
        sections.append(RateSection(label=label, items=_apply_display_settings(items, s, formatter)))
    report = ExchangeRateReport(cbrf_rate=cbr.usd_rub if cbr else None, cbrf_date=cbr.date if cbr else None,
        abcex_buy=abcex[0] if abcex else None, abcex_sell=abcex[1] if abcex else None,
        antarctic_onramp_rate=antarctic.rate if antarctic else None, antarctic_source=antarctic.source if antarctic else "",
        owb_usdc_price=owb, sections=sections,
        source_notes={key: result.note() for key, result in results.items() if result.note()})
    return report.format_for_telegram()


async def recovery_task():
    while True:
        await asyncio.sleep(config.recovery_interval)
        try:
            if monitor.needs_recovery("antarctic") or monitor.needs_recovery("antarctic_tokens"):
                await collector.get("antarctic", fetch_antarctic_quote, force=True)
            else:
                # Refresh is maintained even when no user has a pinned report.
                await token_manager.get_access_token()
                if token_manager.error_kind:
                    await monitor.failure("antarctic_tokens", token_manager.error_kind)
        except Exception as error:
            logger.warning("source=recovery error_kind=%s", type(error).__name__)
