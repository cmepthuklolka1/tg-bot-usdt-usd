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
TOPUP_RATE_URL = "https://app.antarcticwallet.com/api/v3/topup/rub/exchange_rate"
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
    """Returns the USDT/RUB onramp (SBP buy) rate from Antarctic Wallet, or None on failure."""
    access_token = await token_manager.get_access_token()
    if not access_token:
        return None

    session = AsyncSession(impersonate="chrome110")
    try:
        r = await session.get(
            TOPUP_RATE_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=15,
        )

        # Token expired mid-flight — try refresh once
        if r.status_code == 401:
            logger.warning("Antarctic: got 401, attempting refresh")
            if not await token_manager.force_refresh():
                return None
            new_token = await token_manager.get_access_token()
            if not new_token:
                return None
            r = await session.get(
                TOPUP_RATE_URL,
                headers={
                    "Authorization": f"Bearer {new_token}",
                    "Accept": "application/json",
                },
                timeout=15,
            )
            access_token = new_token

        if r.status_code >= 400:
            body = _response_text(r)
            logger.error(
                "Antarctic: topup rate failed, status %s, body: %s",
                r.status_code,
                body,
            )
            fallback_rate = await _fetch_general_usdt_buy_rate(session, access_token)
            if fallback_rate is not None:
                await token_manager._notify_admin(
                    "onramp_fallback",
                    "SBP endpoint Antarctic вернул "
                    f"HTTP {r.status_code}. Использую резервный общий buyRate USDT/RUB. "
                    f"Ответ SBP endpoint: {body or '<empty>'}",
                    title="⚠️ Antarctic Wallet: основной SBP-курс недоступен.",
                    action=(
                        "Действий с токенами сейчас не требуется: access token принят, "
                        "резервный общий курс получен. Если нужен именно SBP/topup-курс, "
                        "проверьте в веб-кабинете Antarctic доступность пополнения через RUB/СБП."
                    ),
                )
                return fallback_rate
            r.raise_for_status()

        r.raise_for_status()
        data = r.json()
        if data.get("status") != "ok":
            logger.warning(f"Antarctic: unexpected status: {data.get('status')}")
            await token_manager._notify_admin(
                "rate_status_not_ok",
                f"API курса вернул неожиданный статус: {data.get('status')}.",
            )
            return None
        rate_obj = data.get("data", {}).get("rate")
        if not rate_obj:
            logger.warning("Antarctic: no rate in response")
            await token_manager._notify_admin(
                "rate_missing",
                "API курса не вернул поле data.rate.",
            )
            return None
        usdt_per_rub = rate_obj["amount"] / (10 ** rate_obj["scale"])
        return round(1.0 / usdt_per_rub, 2)
    except Exception as e:
        logger.error(f"Antarctic: fetch error: {e}")
        await token_manager._notify_admin(
            "fetch_error",
            f"Ошибка при запросе курса: {e}",
        )
        return None
    finally:
        await session.close()
