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
REFRESH_BEFORE_SEC = 86400  # refresh 24h before expiry


class AntarcticTokenManager:
    def __init__(self):
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._expires_at: int = 0
        self._loaded: bool = False
        self._lock = asyncio.Lock()
        self._bot = None
        self._admin_notified: bool = False

    def set_bot(self, bot):
        self._bot = bot

    def _load_tokens(self) -> bool:
        path = config.antarctic_tokens_path
        if not path.exists():
            logger.info("Antarctic: token file not found, skipping")
            return False
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._access_token = data["access_token"]
            self._refresh_token = data["refresh_token"]
            self._expires_at = self._decode_exp(self._access_token)
            self._loaded = True
            logger.info(f"Antarctic: tokens loaded, expires at {self._expires_at}")
            return True
        except Exception as e:
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
            self._admin_notified = False  # reset after successful refresh
            logger.info(f"Antarctic: token refreshed, expires at {self._expires_at}")
            return True
        except Exception as e:
            logger.error(f"Antarctic: refresh exception: {e}")
            return False
        finally:
            await session.close()

    async def _notify_admin(self):
        if self._admin_notified or not self._bot:
            return
        self._admin_notified = True
        try:
            await self._bot.send_message(
                config.admin_id,
                "⚠️ Antarctic Wallet: токен истёк, требуется ручной перелогин.\n"
                "Обновите config/antarctic_tokens.json на сервере.",
            )
        except Exception as e:
            logger.error(f"Antarctic: failed to notify admin: {e}")

    async def get_access_token(self) -> str | None:
        async with self._lock:
            if not self._loaded:
                if not self._load_tokens():
                    return None

            if self._needs_refresh():
                success = await self._do_refresh()
                if not success:
                    await self._notify_admin()
                    return None

            return self._access_token

    async def force_refresh(self) -> bool:
        async with self._lock:
            success = await self._do_refresh()
            if not success:
                await self._notify_admin()
            return success


token_manager = AntarcticTokenManager()


async def fetch_antarctic_sell_rate() -> float | None:
    """Returns the USDT/RUB sell rate from Antarctic Wallet, or None on failure."""
    access_token = await token_manager.get_access_token()
    if not access_token:
        return None

    session = AsyncSession(impersonate="chrome110")
    try:
        r = await session.get(
            f"{API_BASE}/coins/rates",
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
                f"{API_BASE}/coins/rates",
                headers={
                    "Authorization": f"Bearer {new_token}",
                    "Accept": "application/json",
                },
                timeout=15,
            )

        r.raise_for_status()
        data = r.json()
        if data.get("status") != "ok":
            logger.warning(f"Antarctic: unexpected status: {data.get('status')}")
            return None
        for item in data.get("data", {}).get("items", []):
            if item.get("coin") == "USDT":
                return float(item["sellRate"])
        logger.warning("Antarctic: USDT not found in response")
        return None
    except Exception as e:
        logger.error(f"Antarctic: fetch error: {e}")
        return None
    finally:
        await session.close()
