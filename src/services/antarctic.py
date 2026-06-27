"""Antarctic Wallet — fetch USDT/RUB sell rate with auto-refresh."""

import asyncio
import base64
import json
import logging
import time

from curl_cffi.requests import AsyncSession

from ..config import config

logger = logging.getLogger(__name__)

API_BASE = "https://app.antarcticwallet.com/api/v2"
GENERAL_RATES_URL = f"{API_BASE}/coins/rates"
CASH_ONRAMP_RATE_URL = "https://app.antarcticwallet.com/api/v3/buy/crypto/cash/exchange_rate/aw"
ANTARCTIC_SBP_RATE_URL = "https://app.antarcticwallet.com/api/v3/buy/crypto/exchange_rate/aw"
REFRESH_BEFORE_SEC = 86400  # refresh 24h before expiry


def _build_admin_message(
    reason: str,
    *,
    title: str = "⚠️ Antarctic Wallet: курс временно недоступен.",
    action: str = (
        "Что сделать: заново войдите в Antarctic Wallet и обновите "
        "config/antarctic_tokens.json на сервере."
    ),
) -> str:
    return f"{title}\n\nПричина: {reason}\n\n{action}"


class AntarcticTokenManager:
    def __init__(self):
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._expires_at: int = 0
        self._loaded: bool = False
        self._lock = asyncio.Lock()
        self._bot = None
        self._last_notification_key: str | None = None
        self._last_load_error: str = ""

    def set_bot(self, bot):
        self._bot = bot

    def _load_tokens(self) -> bool:
        path = config.antarctic_tokens_path
        if not path.exists():
            logger.info("Antarctic: token file not found, skipping")
            self._last_load_error = "Файл config/antarctic_tokens.json не найден."
            return False
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._access_token = data["access_token"]
            self._refresh_token = data["refresh_token"]
            self._expires_at = self._decode_exp(self._access_token)
            if not self._expires_at:
                self._last_load_error = "Access token не похож на корректный JWT или не содержит exp."
                logger.error("Antarctic: access token has no valid exp")
                return False
            self._loaded = True
            self._last_load_error = ""
            logger.info(f"Antarctic: tokens loaded, expires at {self._expires_at}")
            return True
        except Exception as e:
            self._last_load_error = f"Не удалось прочитать файл токенов: {e}"
            logger.error(f"Antarctic: failed to load tokens: {e}")
            return False

    def _save_tokens(self):
        path = config.antarctic_tokens_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
            }, f, indent=2)
        logger.info("Antarctic: tokens saved to file")

    @staticmethod
    def _decode_exp(token: str) -> int:
        try:
            payload = token.split(".")[1]
            # Add padding
            payload += "=" * (4 - len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload)
            return json.loads(decoded)["exp"]
        except Exception:
            return 0

    def _needs_refresh(self) -> bool:
        return time.time() > (self._expires_at - REFRESH_BEFORE_SEC)

    async def _do_refresh(self) -> bool:
        session = AsyncSession(impersonate="chrome110")
        try:
            r = await session.post(
                f"{API_BASE}/auth/refresh_tokens",
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json={"refresh_token": self._refresh_token},
                timeout=15,
            )
            if r.status_code != 200:
                logger.error(f"Antarctic: refresh failed, status {r.status_code}")
                return False
            data = r.json()
            if data.get("status") != "ok":
                logger.error(f"Antarctic: refresh status: {data.get('status')}")
                return False
            new_data = data["data"]
            self._access_token = new_data["accessToken"]
            self._refresh_token = new_data["refreshToken"]
            self._expires_at = new_data["expiredAt"]
            self._save_tokens()
            self._last_notification_key = None  # reset after successful refresh
            logger.info(f"Antarctic: token refreshed, expires at {self._expires_at}")
            return True
        except Exception as e:
            logger.error(f"Antarctic: refresh exception: {e}")
            return False
        finally:
            await session.close()

    async def _notify_admin(
        self,
        key: str,
        reason: str,
        *,
        title: str = "⚠️ Antarctic Wallet: курс временно недоступен.",
        action: str = (
            "Что сделать: заново войдите в Antarctic Wallet и обновите "
            "config/antarctic_tokens.json на сервере."
        ),
    ):
        if self._last_notification_key == key or not self._bot:
            return
        try:
            await self._bot.send_message(
                config.admin_id,
                _build_admin_message(reason, title=title, action=action),
            )
            self._last_notification_key = key
        except Exception as e:
            logger.error(f"Antarctic: failed to notify admin: {e}")

    async def get_access_token(self) -> str | None:
        async with self._lock:
            if not self._loaded:
                if not self._load_tokens():
                    await self._notify_admin(
                        "load_failed",
                        self._last_load_error or "Не удалось загрузить токены.",
                    )
                    return None

            if self._needs_refresh():
                success = await self._do_refresh()
                if not success:
                    if time.time() >= self._expires_at:
                        # Токен реально истёк — без него не обойтись
                        await self._notify_admin(
                            "expired_refresh_failed",
                            "Access token истёк, а refresh token не смог получить новую пару токенов.",
                        )
                        return None
                    # Рефреш не удался, но токен ещё жив — используем его
                    logger.warning("Antarctic: refresh failed, using current token until expiry")
                    await self._notify_admin(
                        "refresh_failed_token_alive",
                        "Не удалось заранее обновить токены, текущий access token пока ещё работает.",
                    )

            return self._access_token

    async def force_refresh(self) -> bool:
        async with self._lock:
            success = await self._do_refresh()
            if not success:
                await self._notify_admin(
                    "force_refresh_failed",
                    "API вернул 401, но принудительный refresh не смог получить новую пару токенов.",
                )
            return success


token_manager = AntarcticTokenManager()


def _response_text(response, limit: int = 500) -> str:
    text = getattr(response, "text", "") or ""
    return text[:limit]


def _parse_rub_per_usdt_rate(data: dict) -> float | None:
    """Parse current AW onramp rate payload into RUB per 1 USDT."""
    rate_obj = data.get("data", {}).get("rate")
    if not rate_obj:
        return None

    if isinstance(rate_obj, dict):
        try:
            rate = rate_obj["amount"] / (10 ** rate_obj["scale"])
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None
        if rate <= 0:
            return None
        return round(rate, 2)

    try:
        rate = float(str(rate_obj).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if rate <= 0:
        return None

    # The current web app normalizes rates below 1 by inverting them.
    if rate < 1:
        rate = 1.0 / rate
    return round(rate, 2)


def _has_feature_disabled_error(data: dict) -> bool:
    errors = data.get("errors")
    if not isinstance(errors, dict):
        return False
    base_errors = errors.get("base")
    return isinstance(base_errors, list) and "FEATURE_DISABLED" in base_errors


async def _fetch_general_usdt_buy_rate(session: AsyncSession, access_token: str) -> float | None:
    r = await session.get(
        GENERAL_RATES_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=15,
    )
    if r.status_code == 401:
        logger.warning("Antarctic: general rates got 401")
        return None
    if r.status_code >= 400:
        logger.error(
            "Antarctic: general rates failed, status %s, body: %s",
            r.status_code,
            _response_text(r),
        )
        return None
    data = r.json()
    if data.get("status") != "ok":
        logger.warning("Antarctic: general rates unexpected status: %s", data.get("status"))
        return None
    for item in data.get("data", {}).get("items", []):
        if item.get("coin") == "USDT":
            try:
                return round(float(item["buyRate"]), 2)
            except (KeyError, TypeError, ValueError) as e:
                logger.error("Antarctic: failed to parse general USDT buyRate: %s", e)
                return None
    logger.warning("Antarctic: USDT item not found in general rates response")
    return None


async def fetch_antarctic_onramp_rate() -> float | None:
    """Returns the USDT/RUB onramp buy rate from Antarctic Wallet, or None on failure."""
    access_token = await token_manager.get_access_token()
    if not access_token:
        return None

    session = AsyncSession(impersonate="chrome110")
    try:
        async def get_rate_response(url: str):
            nonlocal access_token
            response = await session.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=15,
            )
            if response.status_code != 401:
                return response

            logger.warning("Antarctic: got 401 from %s, attempting refresh", url)
            if not await token_manager.force_refresh():
                return response
            new_token = await token_manager.get_access_token()
            if not new_token:
                return response
            access_token = new_token
            return await session.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=15,
            )

        failures: list[str] = []
        alert_failures: list[str] = []
        endpoints = [
            ("cash onramp", CASH_ONRAMP_RATE_URL),
            ("Antarctic SBP", ANTARCTIC_SBP_RATE_URL),
        ]

        for index, (label, url) in enumerate(endpoints):
            r = await get_rate_response(url)
            if r.status_code >= 400:
                body = _response_text(r)
                failure = f"{label}: HTTP {r.status_code}, body: {body or '<empty>'}"
                failures.append(failure)
                try:
                    data = r.json()
                except Exception:
                    data = {}
                if label == "cash onramp" and _has_feature_disabled_error(data):
                    logger.info(
                        "Antarctic: %s rate disabled by feature flag, using next endpoint",
                        label,
                    )
                else:
                    alert_failures.append(failure)
                    logger.error(
                        "Antarctic: %s rate failed, status %s, body: %s",
                        label,
                        r.status_code,
                        body,
                    )
                continue

            r.raise_for_status()
            data = r.json()
            if data.get("status") != "ok":
                failures.append(f"{label}: unexpected status {data.get('status')}")
                logger.warning("Antarctic: %s unexpected status: %s", label, data.get("status"))
                continue

            rate = _parse_rub_per_usdt_rate(data)
            if rate is None:
                failures.append(f"{label}: response has no valid data.rate")
                logger.warning("Antarctic: %s response has no valid data.rate", label)
                continue

            if index > 0:
                if alert_failures:
                    await token_manager._notify_admin(
                        "onramp_secondary_fallback",
                        "Основной cash onramp endpoint Antarctic недоступен. "
                        f"Использую резервный Antarctic SBP endpoint. "
                        f"Проблема: {'; '.join(alert_failures)}",
                        title="⚠️ Antarctic Wallet: основной onramp-курс недоступен.",
                        action=(
                            "Действий с токенами сейчас не требуется: access token принят, "
                            "резервный Antarctic SBP-курс получен. Если нужен именно курс "
                            "«Счёт по реквизитам», проверьте его доступность в веб-кабинете."
                        ),
                    )
            return rate

        if alert_failures:
            logger.error(
                "Antarctic: onramp rate endpoints failed: %s",
                "; ".join(alert_failures),
            )
            fallback_rate = await _fetch_general_usdt_buy_rate(session, access_token)
            if fallback_rate is not None:
                await token_manager._notify_admin(
                    "onramp_fallback",
                    "Onramp endpoints Antarctic недоступны. "
                    f"Использую резервный общий buyRate USDT/RUB. "
                    f"Проблемы onramp endpoints: {'; '.join(alert_failures)}",
                    title="⚠️ Antarctic Wallet: основной onramp-курс недоступен.",
                    action=(
                        "Действий с токенами сейчас не требуется: access token принят, "
                        "резервный общий курс получен. Если нужен именно курс со страницы "
                        "/onramp, проверьте в веб-кабинете Antarctic доступность пополнения RUB."
                    ),
                )
                return fallback_rate

        await token_manager._notify_admin(
            "rate_missing",
            "API курса не вернул валидный onramp rate. "
            f"Проблемы endpoints: {'; '.join(failures) or '<нет деталей>'}.",
        )
        return None
    except Exception as e:
        logger.error(f"Antarctic: fetch error: {e}")
        await token_manager._notify_admin(
            "fetch_error",
            f"Ошибка при запросе курса: {e}",
        )
        return None
    finally:
        await session.close()
