import json
import logging
from ..config import config

logger = logging.getLogger(__name__)

class WhitelistStorage:
    def __init__(self, path=config.whitelist_path):
        self.path = path
    
    def _read_data(self) -> dict:
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error reading whitelist: {e}")
            return {"users": []}

    def _write_data(self, data: dict):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    def is_allowed(self, user_id: int) -> bool:
        if user_id == config.admin_id:
            return True
        users = self._read_data().get("users", [])
        return user_id in users

    def add_user(self, user_id: int) -> bool:
        data = self._read_data()
        users = data.get("users", [])
        if user_id not in users:
            users.append(user_id)
            data["users"] = users
            self._write_data(data)
            return True
        return False

    def remove_user(self, user_id: int) -> bool:
        data = self._read_data()
        users = data.get("users", [])
        if user_id in users:
            users.remove(user_id)
            data["users"] = users
            self._write_data(data)
        return False

class BannedSellersStorage:
    def __init__(self, path=config.banned_sellers_path):
        self.path = path
    
    def _read_data(self) -> dict:
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error reading banned sellers: {e}")
            return {"banned": []}

    def _write_data(self, data: dict):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    def get_banned(self) -> set[str]:
        data = self._read_data()
        return set(data.get("banned", []))

    def ban_seller(self, username: str) -> bool:
        data = self._read_data()
        banned = data.get("banned", [])
        if username.lower() not in [u.lower() for u in banned]:
            banned.append(username)
            data["banned"] = banned
            self._write_data(data)
            return True
        return False

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
            data["banned"] = banned
            self._write_data(data)
            return True
        return False

class PinnedMessageStorage:
    def __init__(self, path="config/pinned_messages.json"):
        self.path = path
    
    def _read_data(self) -> dict:
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"pinned": {}}

    def _write_data(self, data: dict):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    def get_all(self) -> dict:
        return self._read_data().get("pinned", {})

    def set_pinned(self, user_id: int, message_id: int):
        data = self._read_data()
        pinned = data.get("pinned", {})
        pinned[str(user_id)] = message_id
        data["pinned"] = pinned
        self._write_data(data)

    def remove_pinned(self, user_id: int):
        data = self._read_data()
        pinned = data.get("pinned", {})
        pinned.pop(str(user_id), None)
        data["pinned"] = pinned
        self._write_data(data)
