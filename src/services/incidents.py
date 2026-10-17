"""Persisted source incidents, independent of token refresh and Telegram clients."""

import asyncio
import json
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import config
from ..utils.storage import _write_json_atomic

logger = logging.getLogger(__name__)
REASONS = {
    "network_timeout": "Истёк таймаут соединения с сервисом.",
    "network_error": "Не удалось установить соединение с сервисом.",
    "rate_limited": "Сервис временно ограничил частоту запросов.",
    "upstream_error": "Сервис временно отвечает с ошибкой.",
    "access_denied": "Сервис запретил доступ. Возможна блокировка запроса или ограничение прав; это не подтверждает недействительность токена.",
    "invalid_response": "Сервис вернул неожиданный формат данных.",
    "auth_rejected": "Сервис отклонил обновление авторизации.",
    "configuration_error": "Файл токенов отсутствует или некорректен.",
    "storage_error": "Не удалось сохранить обновлённые токены на диск.",
    "degraded": "Основной курс недоступен; используется явно обозначенный резервный курс.",
}
MANUAL = {"auth_rejected", "configuration_error", "storage_error"}


class IncidentMonitor:
    def __init__(self, path, sender=None, *, failure_threshold=None, reminder=None):
        self.path = Path(path)
        self.sender = sender
        self.threshold = failure_threshold or config.notification_failures
        self.reminder = reminder or config.notification_reminder
        self._lock = asyncio.Lock()
        try:
            data = json.loads(self.path.read_text())
            self.states = {}
            if isinstance(data, dict):
                for key, state in data.items():
                    if not isinstance(state, dict):
                        continue
                    count = state.get("failures", 0)
                    stamps = [state[name] for name in ("started_at", "notified_at", "last_success_at") if name in state]
                    if type(count) is not int or count < 0 or any(type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0 for stamp in stamps):
                        continue
                    self.states[key] = state
        except (OSError, ValueError):
            self.states = {}

    def _save(self):
        try:
            _write_json_atomic(self.path, self.states, ensure_ascii=False)
        except OSError:
            logger.error("source=incidents error_kind=storage_error")

    def needs_recovery(self, source):
        state = self.states.get(source, {})
        return bool(state.get("failures") or state.get("pending_recovery"))

    async def _send(self, text):
        if self.sender is None:
            return False
        try:
            await asyncio.wait_for(self.sender(text), timeout=5)
            return True
        except Exception as error:
            logger.warning("source=notifications error_kind=%s", type(error).__name__)
            return False

    async def failure(self, source, kind, *, now=None):
        now = time.time() if now is None else now
        async with self._lock:
            old = self.states.get(source, {})
            state = dict(old)
            state.update(kind=kind, failures=old.get("failures", 0) + 1,
                         started_at=old.get("started_at", now), pending_recovery=False)
            self.states[source] = state
            important = kind in MANUAL
            last = old.get("notified_at")
            escalate = important and old.get("notified_kind") != kind
            if (important or state["failures"] >= self.threshold) and (last is None or now-last >= self.reminder or escalate):
                name = "Antarctic Wallet" if source.startswith("antarctic") else source
                if kind in {"auth_rejected", "configuration_error"}:
                    action = "Заново войдите в Antarctic Wallet и обновите config/antarctic_tokens.json на сервере. Бот подхватит корректный файл автоматически."
                elif kind == "storage_error":
                    action = "Проверьте свободное место и права записи. Новые токены сохранены в памяти, бот повторит запись."
                else:
                    action = f"Перевыпуск токенов не требуется. Автоматическая проверка — каждые {config.recovery_interval:g} секунд."
                message = f"⚠️ {name}: {'требуется действие' if important else 'временный сбой'}.\n\n{REASONS.get(kind, REASONS['invalid_response'])}\n\n{action}"
                if await self._send(message):
                    state.update(notified_at=now, notified_kind=kind, notified=True)
            self._save()

    async def success(self, source, *, now=None):
        now = time.time() if now is None else now
        async with self._lock:
            old = self.states.get(source, {})
            if old.get("notified"):
                duration = max(0, int(now-old.get("started_at", now)))
                when = datetime.fromtimestamp(now, timezone(timedelta(hours=3))).strftime("%d.%m %H:%M:%S")
                name = "Antarctic Wallet" if source.startswith("antarctic") else source
                title = "авторизация / сохранение токенов восстановлены" if source == "antarctic_tokens" else "курс снова доступен, работа восстановлена"
                action = "Доступность курса проверяется отдельно." if source == "antarctic_tokens" else "Действий не требуется."
                if not await self._send(f"✅ {name}: {title}.\n\nВремя: {when} МСК. Сбой длился {duration // 60} мин {duration % 60} сек. {action}"):
                    self.states[source] = {**old, "failures": 0, "pending_recovery": True}
                    self._save()
                    return
            self.states[source] = {"last_success_at": now}
            self._save()


monitor = IncidentMonitor(config.runtime_state_path)
