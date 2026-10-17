import os
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from scripts.release import validate_health, release_environment, activate


class ReleaseTests(unittest.TestCase):
    def test_health_requires_expected_version_pid_and_fresh_heartbeat(self):
        good = {"version":"abc", "pid":10, "checked_at":100, "last_success":{"antarctic":99}}
        self.assertTrue(validate_health(good, "abc", 10, 95, now=105))
        for changes in ({"pid":11}, {"version":"old"}, {"checked_at":90}, {"last_success":{}}):
            self.assertFalse(validate_health({**good, **changes}, "abc", 10, 95, now=105))

    def test_release_tests_do_not_inherit_real_credentials(self):
        env = release_environment({"BOT_TOKEN":"real-secret", "ADMIN_ID":"999", "BOT_ENV_FILE":"/real/.env"})
        self.assertEqual(env["BOT_ENV_FILE"], os.devnull)
        self.assertNotEqual(env["BOT_TOKEN"], "real-secret")
        self.assertEqual(env["ADMIN_ID"], "1")

    def test_failed_activation_restores_previous_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "config").mkdir()
            candidate = base / "candidate"
            candidate.mkdir()
            (candidate / ".prepared").touch()
            unit_root = base / "units"
            override = unit_root / "test.service.d/release.conf"
            override.parent.mkdir(parents=True)
            override.write_bytes(b"previous configuration")
            calls = []
            def command(*args):
                calls.append(args)
                if args[0] == "install":
                    shutil.copyfile(args[-2], args[-1])
            with patch("scripts.release.privileged", side_effect=command), self.assertRaisesRegex(RuntimeError, "health"):
                activate(base, candidate, "new", "test", unit_root=unit_root, timeout=0)
            self.assertEqual(override.read_bytes(), b"previous configuration")
            self.assertEqual(calls.count(("systemctl", "restart", "test")), 2)

    def test_successful_activation_requires_fresh_source_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "config").mkdir()
            (base / "config/health.json").write_text(json.dumps({"version":"new", "pid":10, "checked_at":100, "last_success":{"antarctic":100}}))
            candidate = base / "candidate"
            candidate.mkdir()
            (candidate / ".prepared").touch()
            def command(*args):
                if args[0] == "mkdir":
                    Path(args[-1]).mkdir(parents=True, exist_ok=True)
                if args[0] == "install":
                    shutil.copyfile(args[-2], args[-1])
            with patch("scripts.release.privileged", side_effect=command), patch("scripts.release.subprocess.check_output", return_value=b"10"), patch("scripts.release.time.time", return_value=100):
                activate(base, candidate, "new", "test", unit_root=base/"units")
