import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from src.services.incidents import IncidentMonitor


class IncidentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state.json"
        self.send = AsyncMock()
        self.monitor = IncidentMonitor(self.path, self.send, failure_threshold=2, reminder=3600)

    async def test_failure_success_failure_opens_two_incidents_and_recovers(self):
        for _ in range(2):
            await self.monitor.failure("antarctic", "network_timeout", now=10)
        self.assertEqual(self.send.await_count, 1)
        self.assertNotIn("обновите", self.send.call_args.args[0])
        await self.monitor.success("antarctic", now=20)
        self.assertEqual(self.send.await_count, 2)
        self.assertIn("восстанов", self.send.call_args.args[0])
        for _ in range(2):
            await self.monitor.failure("antarctic", "network_timeout", now=30)
        self.assertEqual(self.send.await_count, 3)

    async def test_alternating_transient_errors_do_not_spam(self):
        for i, kind in enumerate(["network_timeout", "upstream_error", "network_error", "invalid_response"]):
            await self.monitor.failure("antarctic", kind, now=10+i)
        self.assertEqual(self.send.await_count, 1)

    async def test_restart_keeps_incident_and_failed_delivery_is_retried(self):
        self.send.side_effect = OSError("Telegram down")
        await self.monitor.failure("antarctic", "auth_rejected", now=10)
        self.send.side_effect = None
        other = IncidentMonitor(self.path, self.send, failure_threshold=2)
        await other.failure("antarctic", "auth_rejected", now=20)
        self.assertEqual(self.send.await_count, 2)
        self.assertIn("обновите", self.send.call_args.args[0])
        await other.success("antarctic", now=30)
        self.assertIn("восстанов", self.send.call_args.args[0])

    async def test_degraded_does_not_claim_main_source_recovered(self):
        await self.monitor.failure("antarctic", "network_timeout", now=10)
        await self.monitor.failure("antarctic", "network_timeout", now=20)
        await self.monitor.failure("antarctic", "degraded", now=30)
        self.assertEqual(self.send.await_count, 1)
        self.assertTrue(self.monitor.needs_recovery("antarctic"))

    async def test_failed_recovery_delivery_survives_restart(self):
        await self.monitor.failure("antarctic", "auth_rejected", now=10)
        self.send.side_effect = OSError()
        await self.monitor.success("antarctic", now=20)
        other = IncidentMonitor(self.path, self.send)
        self.send.side_effect = None
        await other.success("antarctic", now=30)
        self.assertIn("восстанов", self.send.call_args.args[0])

    async def test_auth_failure_escalates_an_existing_network_incident(self):
        await self.monitor.failure("antarctic", "network_timeout", now=10)
        await self.monitor.failure("antarctic", "network_timeout", now=20)
        await self.monitor.failure("antarctic", "auth_rejected", now=30)
        self.assertEqual(self.send.await_count, 2)
        self.assertIn("обновите", self.send.call_args.args[0])

    async def test_token_repair_does_not_claim_rate_has_recovered(self):
        await self.monitor.failure("antarctic", "network_timeout", now=10)
        await self.monitor.failure("antarctic", "network_timeout", now=20)
        await self.monitor.failure("antarctic_tokens", "auth_rejected", now=30)
        await self.monitor.success("antarctic_tokens", now=40)
        text = self.send.call_args.args[0]
        self.assertIn("авторизац", text)
        self.assertIn("отдельно", text)
        self.assertNotIn("Действий не требуется", text)
        self.assertTrue(self.monitor.needs_recovery("antarctic"))

    async def test_invalid_persisted_state_does_not_break_monitor(self):
        self.path.write_text('{"antarctic": []}')
        other = IncidentMonitor(self.path, self.send, failure_threshold=1)
        await other.failure("antarctic", "network_timeout", now=10)
        self.assertTrue(other.needs_recovery("antarctic"))
