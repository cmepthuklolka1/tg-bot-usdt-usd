"""Antarctic quotes and durable rotating credentials, without Telegram coupling."""

import asyncio
import base64
import json
import logging
import math
import time
from dataclasses import dataclass

from curl_cffi.requests import AsyncSession

from ..config import config
from ..utils.http import HTTPFailure, check_response, classify_error, get_session, request_timeout
from ..utils.retry import DEFAULT_RETRY
from ..utils.storage import _write_json_atomic

logger = logging.getLogger(__name__)
API_BASE = "https://app.antarcticwallet.com/api/v2"
GENERAL_RATES_URL = f"{API_BASE}/coins/rates"
CASH_ONRAMP_RATE_URL = "https://app.antarcticwallet.com/api/v3/buy/crypto/cash/exchange_rate/aw"
ANTARCTIC_SBP_RATE_URL = "https://app.antarcticwallet.com/api/v3/buy/crypto/exchange_rate/aw"
REFRESH_BEFORE_SEC = 86400


def _session():
    return get_session("antarctic", factory=AsyncSession)


def _build_admin_message(reason, *, title="⚠️ Antarctic Wallet: временный сбой.",
                         action="Перевыпуск токенов не требуется. Бот повторит проверку автоматически."):
    return f"{title}\n\nПричина: {reason}\n\n{action}"


class AntarcticTokenManager:
    def __init__(self):
        self._access_token = ""
        self._refresh_token = ""
        self._expires_at = 0
        self._loaded = False
        self._lock = asyncio.Lock()
        self._signature = None
        self._dirty = False
        self._next_refresh = 0.0
        self._refresh_task = None
        self.error_kind = None

    @staticmethod
    def _decode_exp(token):
        try:
            payload = token.split(".")[1]
            value = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["exp"]
            return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            return 0

    def _file_signature(self):
        stat = config.antarctic_tokens_path.stat()
        return (stat.st_ino, stat.st_mtime_ns, stat.st_size)

    def _load_tokens(self):
        try:
            signature = self._file_signature()
            if self._loaded and signature == self._signature:
                return True
            data = json.loads(config.antarctic_tokens_path.read_text(encoding="utf-8"))
            access, refresh = data["access_token"], data["refresh_token"]
            expiry = self._decode_exp(access)
            if not expiry or not isinstance(refresh, str) or not refresh.strip():
                raise ValueError("Invalid token pair")
            self._access_token, self._refresh_token, self._expires_at = access, refresh, expiry
            self._signature, self._loaded, self._dirty = signature, True, False
            self._next_refresh = 0
            self.error_kind = None
            return True
        except (OSError, ValueError, TypeError, KeyError):
            self.error_kind = "configuration_error"
            logger.warning("source=antarctic_tokens error_kind=configuration_error")
            return False

    def _save_tokens(self):
        _write_json_atomic(config.antarctic_tokens_path, {"access_token": self._access_token, "refresh_token": self._refresh_token})
        self._signature = self._file_signature()
        self._dirty = False

    def _persist(self):
        try:
            self._save_tokens()
            self.error_kind = None
        except OSError:
            self.error_kind = "storage_error"
            logger.error("source=antarctic_tokens error_kind=storage_error rotated_pair_in_memory=true")

    def _needs_refresh(self):
        return time.time() > self._expires_at - REFRESH_BEFORE_SEC

    async def _do_refresh(self):
        self._next_refresh = time.monotonic() + config.recovery_interval
        try:
            response = await _session().post(
                f"{API_BASE}/auth/refresh_tokens",
                headers={"Authorization": f"Bearer {self._access_token}", "Accept": "application/json"},
                json={"refresh_token": self._refresh_token}, timeout=request_timeout())
            check_response(response)
            data = response.json()
            if not isinstance(data, dict) or data.get("status") != "ok":
                raise ValueError("Invalid refresh response")
            pair = data["data"]
            access, refresh, expiry = pair["accessToken"], pair["refreshToken"], pair["expiredAt"]
            decoded_expiry = self._decode_exp(access)
            if (not isinstance(refresh, str) or not refresh.strip() or isinstance(expiry, bool)
                    or not isinstance(expiry, (int, float)) or not math.isfinite(expiry)
                    or min(expiry, decoded_expiry) <= time.time()):
                raise ValueError("Invalid refreshed token pair")
            # A manual replacement made while HTTP was in flight takes priority.
            try:
                changed = self._file_signature() != self._signature
            except OSError:
                changed = False
            if changed and self._load_tokens():
                logger.info("source=antarctic_tokens event=manual_replacement_preserved")
                return True
            self._access_token, self._refresh_token = access, refresh
            self._expires_at = int(min(expiry, decoded_expiry))
            self._loaded, self._dirty = True, True
            self._persist()
            logger.info("source=antarctic_tokens event=refreshed expires_at=%s persisted=%s", self._expires_at, not self._dirty)
            return True
        except Exception as error:
            self.error_kind = classify_error(error)
            logger.warning("source=antarctic_tokens error_kind=%s", self.error_kind)
            return False

    async def get_access_token(self):
        async with self._lock:
            # Never reload the old on-disk pair after a rotated pair failed to save.
            if self._dirty:
                self._persist()
            else:
                self._load_tokens()
            if not self._loaded:
                return None
            due = self._needs_refresh() and time.monotonic() >= self._next_refresh
            current_token = self._access_token
        if due:
            await self._refresh(current_token)
        return self._access_token if time.time() < self._expires_at else None

    async def force_refresh(self, rejected_token=None):
        return await self._refresh(rejected_token)

    async def _refresh(self, rejected_token):
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._refresh_locked(rejected_token))
        # An endpoint/report timeout must not abandon a rotating credential POST.
        return await asyncio.shield(self._refresh_task)

    async def _refresh_locked(self, rejected_token):
        async with self._lock:
            if rejected_token is not None and self._access_token != rejected_token:
                return True
            if time.monotonic() < self._next_refresh and self.error_kind:
                return False
            return await self._do_refresh()

    async def close(self):
        if self._refresh_task is not None:
            await asyncio.shield(self._refresh_task)


token_manager = AntarcticTokenManager()


def _parse_rub_per_usdt_rate(data: dict) -> float | None:
    """Parse current AW onramp rate payload into RUB per 1 USDT."""
    if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
        return None
    rate_obj = data["data"].get("rate")
    if not rate_obj:
        return None

    if isinstance(rate_obj, dict):
        try:
            if not isinstance(rate_obj.get("scale"), int) or not 0 <= rate_obj["scale"] <= 18:
                return None
            rate = rate_obj["amount"] / (10 ** rate_obj["scale"])
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None
        if not math.isfinite(rate) or rate <= 0:
            return None
        return round(rate, 2)

    try:
        rate = float(str(rate_obj).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(rate) or rate <= 0:
        return None

    # The current web app normalizes rates below 1 by inverting them.
    if rate < 1:
        rate = 1.0 / rate
    return round(rate, 2)


def _has_feature_disabled_error(data):
    errors = data.get("errors") if isinstance(data, dict) else None
    return isinstance(errors, dict) and isinstance(errors.get("base"), list) and "FEATURE_DISABLED" in errors["base"]


@dataclass(frozen=True)
class AntarcticQuote:
    rate: float | None
    source: str = ""
    degraded: bool = False
    error_kind: str | None = None


@DEFAULT_RETRY
async def _rate_request(url, access_token):
    response = await _session().get(url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}, timeout=request_timeout())
    # Preserve 422 FEATURE_DISABLED for the source-selection policy.
    if response.status_code not in (401, 422):
        check_response(response)
    return response


async def _response_with_auth(url, access_token):
    response = await _rate_request(url, access_token)
    if response.status_code == 401:
        if not await token_manager.force_refresh(access_token):
            # A network failure during refresh does not prove invalid credentials.
            raise TokenFailure(token_manager.error_kind or "invalid_response")
        access_token = await token_manager.get_access_token()
        if not access_token:
            raise TokenFailure(token_manager.error_kind or "invalid_response")
        response = await _rate_request(url, access_token)
        if response.status_code == 401:
            # Refresh was accepted. Further endpoint rejection needs diagnosis,
            # not another rotation or an unsupported instruction to log in again.
            raise TokenFailure("access_denied")
    return response, access_token


class TokenFailure(Exception):
    def __init__(self, kind):
        self.kind = kind
        super().__init__(kind)


async def _fetch_quote():
    started = time.monotonic()
    access_token = await token_manager.get_access_token()
    if not access_token:
        return AntarcticQuote(None, error_kind=token_manager.error_kind or "configuration_error")
    failures = []
    endpoints = [("cash onramp", CASH_ONRAMP_RATE_URL), ("Antarctic SBP", ANTARCTIC_SBP_RATE_URL), ("общий buyRate (резерв)", GENERAL_RATES_URL)]
    for index, (label, url) in enumerate(endpoints):
        try:
            # Give each endpoint a share of the remaining overall budget.
            remaining_count = len(endpoints) - index
            remaining = config.source_timeout - (time.monotonic() - started)
            response, access_token = await asyncio.wait_for(_response_with_auth(url, access_token), timeout=max(.01, remaining / remaining_count))
            data = response.json()
            if label == "cash onramp" and response.status_code == 422 and _has_feature_disabled_error(data):
                logger.info("source=antarctic endpoint=cash event=feature_disabled")
                continue
            check_response(response)
            if not isinstance(data, dict) or data.get("status") != "ok":
                raise ValueError("Invalid quote response")
            if url == GENERAL_RATES_URL:
                rate = next((float(item["buyRate"]) for item in data["data"]["items"] if item.get("coin") == "USDT"), None)
                if rate is None or not math.isfinite(rate) or rate <= 0:
                    raise ValueError("Invalid general quote")
                rate = round(rate, 2)
            else:
                rate = _parse_rub_per_usdt_rate(data)
                if rate is None:
                    raise ValueError("Invalid onramp quote")
            logger.info("source=antarctic endpoint=%s event=quote_received duration_ms=%d degraded=%s", label, (time.monotonic()-started)*1000, bool(failures))
            return AntarcticQuote(rate, source=label, degraded=bool(failures), error_kind="degraded" if failures else None)
        except Exception as error:
            kind = error.kind if isinstance(error, TokenFailure) else classify_error(error)
            failures.append(kind)
            logger.warning("source=antarctic endpoint=%s error_kind=%s http_status=%s", label, kind, getattr(error, "status", None))
            if isinstance(error, TokenFailure) or kind == "auth_rejected":
                return AntarcticQuote(None, error_kind=kind)
    return AntarcticQuote(None, error_kind=failures[-1] if failures else "invalid_response")


async def fetch_antarctic_quote():
    try:
        return await asyncio.wait_for(_fetch_quote(), timeout=config.source_timeout)
    except TimeoutError:
        return AntarcticQuote(None, error_kind="network_timeout")


async def fetch_antarctic_onramp_rate():
    """Compatibility API. New callers retain provenance via fetch_antarctic_quote."""
    return (await fetch_antarctic_quote()).rate
