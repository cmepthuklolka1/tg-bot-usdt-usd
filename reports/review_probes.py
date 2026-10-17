"""Run the permanent regression suite replacing the historical defect probes.

The 2026-10-17 audit probes deliberately asserted broken behavior. That
behavior is now fixed; the corresponding regression tests assert the desired
behavior instead. No real credentials or API requests are used.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.release import release_environment

if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=Path(__file__).resolve().parents[1], env=release_environment()))
