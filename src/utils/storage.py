import json
import logging
import os
import tempfile
import threading
from copy import deepcopy
from functools import wraps
from pathlib import Path
from ..config import config

logger = logging.getLogger(__name__)
_FILE_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path) -> threading.RLock:
    key = str(Path(path).resolve())
    with _LOCKS_GUARD:
        return _FILE_LOCKS.setdefault(key, threading.RLock())



def _transaction(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with _lock_for(self.path):
            return method(self, *args, **kwargs)
    return wrapped


def _validate_settings(exchange, entry):
    if exchange not in DISPLAY_DEFAULTS:
        raise ValueError("Unknown exchange")
    mode, value = entry.get("mode"), entry.get("value")
    if mode == "sequential":
        valid = type(value) is int and 1 <= value <= 50
    elif mode == "positions":
        valid = isinstance(value, list) and 1 <= len(value) <= 100 and all(type(v) is int and 1 <= v <= 100 for v in value)
    else:
        valid = False
    if not valid:
        raise ValueError("Invalid display mode or positions")
    if exchange.startswith("bestchange"):
        if entry.get("payment") not in {"sberbank", "vtb", "tinkoff", "alfaclick"} or entry.get("coin") not in {"tether-bep20", "tether-trc20", "tether-erc20", "tether-ton"}:
            raise ValueError("Invalid source settings")
    else:
        amount = entry.get("max_amount")
        if type(amount) is not int or not 1000 <= amount <= 100000000:
            raise ValueError("Invalid trade amount")
    return entry


def _read_store(path, key, expected):
    with _lock_for(path):
        try:
            with open(path, encoding="utf-8") as source:
                data = json.load(source)
            if not isinstance(data, dict) or not isinstance(data.get(key), expected):
                raise ValueError("Unexpected store shape")
            if key == "users" and expected is list and any(type(uid) is not int for uid in data[key]):
                raise ValueError("Invalid user ID")
            if key == "banned" and any(not isinstance(name, str) for name in data[key]):
                raise ValueError("Invalid seller name")
            return data
        except (OSError, ValueError):
            logger.warning("store=%s event=missing_or_invalid", Path(path).name)
            return {key: expected()}

def _write_json_atomic(path, data: dict, *, ensure_ascii: bool = True):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_for(target)
    with lock:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=ensure_ascii)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, target)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

class WhitelistStorage:
    def __init__(self, path=config.whitelist_path):
        self.path = path

    def _read_data(self) -> dict:
        return _read_store(self.path, "users", list)

    def _write_data(self, data: dict):
        _write_json_atomic(self.path, data)

    def is_allowed(self, user_id: int) -> bool:
        if user_id == config.admin_id:
            return True
        users = self._read_data().get("users", [])
        return user_id in users

    @_transaction
    def add_user(self, user_id: int) -> bool:
        data = self._read_data()
        users = data.get("users", [])
        if user_id not in users:
            users.append(user_id)
            data["users"] = users
            self._write_data(data)
            return True
        return False

    @_transaction
    def remove_user(self, user_id: int) -> bool:
        data = self._read_data()
        users = data.get("users", [])
        if user_id in users:
            users.remove(user_id)
            data["users"] = users
            self._write_data(data)
            return True
        return False

class BannedSellersStorage:
    def __init__(self, path=config.banned_sellers_path):
        self.path = path

    def _read_data(self) -> dict:
        return _read_store(self.path, "banned", list)

    def _write_data(self, data: dict):
        _write_json_atomic(self.path, data)

    def get_banned(self) -> set[str]:
        data = self._read_data()
        return set(data.get("banned", []))

    @_transaction
    def ban_seller(self, username: str) -> bool:
        data = self._read_data()
        banned = data.get("banned", [])
        if username.lower() not in [u.lower() for u in banned]:
            banned.append(username)
            data["banned"] = banned
            self._write_data(data)
            return True
        return False

    @_transaction
    def unban_seller(self, username: str) -> bool:
        data = self._read_data()
        banned = data.get("banned", [])

        # Находим пользователя без учёта регистра
        user_to_remove = None
        for u in banned:
            if u.lower() == username.lower():
                user_to_remove = u
                break

        if user_to_remove:
            banned.remove(user_to_remove)
            data["banned"] = banned
            self._write_data(data)
            return True
        return False

DISPLAY_DEFAULTS = {
    "bestchange_1": {
        "mode": "positions", "value": [1, 5, 10],
        "payment": "sberbank", "coin": "tether-bep20",
    },
    "bestchange_2": {
        "mode": "positions", "value": [1, 5, 10],
        "payment": "vtb", "coin": "tether-bep20",
    },
    "bybit_1": {"mode": "sequential", "value": 5, "max_amount": 100000},
    "bybit_2": {"mode": "sequential", "value": 5, "max_amount": 50000},
}


class UserSettingsStorage:
    def __init__(self, path=config.user_settings_path):
        self.path = path

    def _read_data(self) -> dict:
        return _read_store(self.path, "users", dict)

    def _write_data(self, data: dict):
        _write_json_atomic(self.path, data, ensure_ascii=False)

    def get_exchange_settings(self, user_id: int, exchange: str) -> dict:
        """Возвращает настройки отображения для конкретной биржи.
        Если у пользователя нет настроек — возвращает дефолт."""
        data = self._read_data()
        user_settings = data.get("users", {}).get(str(user_id), {})
        defaults = deepcopy(DISPLAY_DEFAULTS.get(exchange, {}))
        try:
            candidate = {**defaults, **user_settings.get(exchange, {})}
            return deepcopy(_validate_settings(exchange, candidate))
        except (ValueError, TypeError, AttributeError):
            return defaults

    @_transaction
    def set_exchange_settings(self, user_id: int, exchange: str, mode: str, value,
                              payment: str = None, coin: str = None,
                              max_amount: int = None):
        """Сохраняет настройки отображения для конкретной биржи.
        payment/coin актуальны для BestChange, max_amount — для Bybit.
        Если необязательные параметры не переданы — существующие значения сохраняются."""
        data = self._read_data()
        users = data.get("users", {})
        if not isinstance(users.get(str(user_id)), dict):
            users[str(user_id)] = {}
        # Берём текущие значения, чтобы не затирать поля которые не обновляем
        existing = self.get_exchange_settings(user_id, exchange)
        entry = {"mode": mode, "value": value}
        resolved_payment = payment if payment is not None else existing.get("payment")
        resolved_coin = coin if coin is not None else existing.get("coin")
        resolved_max_amount = max_amount if max_amount is not None else existing.get("max_amount")
        if resolved_payment is not None:
            entry["payment"] = resolved_payment
        if resolved_coin is not None:
            entry["coin"] = resolved_coin
        if resolved_max_amount is not None:
            entry["max_amount"] = resolved_max_amount
        _validate_settings(exchange, entry)
        users[str(user_id)][exchange] = entry
        data["users"] = users
        self._write_data(data)

    @_transaction
    def get_all_settings(self, user_id: int) -> dict:
        """Возвращает настройки пользователя для всех бирж (с дефолтами)."""
        return {
            key: self.get_exchange_settings(user_id, key)
            for key in DISPLAY_DEFAULTS
        }


class PinnedMessageStorage:
    def __init__(self, path=config.pinned_messages_path):
        self.path = path

    def _read_data(self) -> dict:
        return _read_store(self.path, "pinned", dict)

    def _write_data(self, data: dict):
        _write_json_atomic(self.path, data)

    def get_all(self) -> dict:
        return self._read_data().get("pinned", {})

    @_transaction
    def set_pinned(self, user_id: int, message_id: int):
        data = self._read_data()
        pinned = data.get("pinned", {})
        pinned[str(user_id)] = message_id
        data["pinned"] = pinned
        self._write_data(data)

    @_transaction
    def remove_pinned(self, user_id: int):
        data = self._read_data()
        pinned = data.get("pinned", {})
        pinned.pop(str(user_id), None)
        data["pinned"] = pinned
        self._write_data(data)
