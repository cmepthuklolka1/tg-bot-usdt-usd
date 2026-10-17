"""Prepare an immutable release, then activate it with health checks and rollback."""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path


def release_environment(source=None):
    env = dict(os.environ if source is None else source)
    env.update(BOT_TOKEN="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", ADMIN_ID="1",
               BOT_ENV_FILE=os.devnull, PYTHONDONTWRITEBYTECODE="1")
    for key in ("RUNTIME_STATE_PATH", "ANTARCTIC_TOKENS_PATH", "WHITELIST_PATH", "PINNED_MESSAGES_PATH", "USER_SETTINGS_PATH", "BANNED_SELLERS_PATH"):
        env.pop(key, None)
    return env


def validate_health(data, version, pid, started, *, now=None):
    now = time.time() if now is None else now
    return (data.get("version") == version and data.get("pid") == pid
            and started <= data.get("checked_at", 0) <= now
            and now-data.get("checked_at", 0) <= 60
            and any(started <= stamp <= now for stamp in data.get("last_success", {}).values()))


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def privileged(*args):
    return run(*(("sudo",) if os.geteuid() else ()), *args)


def git(base, *args):
    return subprocess.check_output(["git", "-c", f"safe.directory={base}", "-C", str(base), *args])


def prepare(base, ref):
    dirty = git(base, "status", "--porcelain", "--untracked-files=no").decode()
    if dirty:
        raise RuntimeError("Tracked files are modified; preserve or commit them before deployment")
    version = git(base, "rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    releases = base / ".releases"
    releases.mkdir(exist_ok=True)
    release = releases / version
    if release.exists():
        if (release / ".prepared").exists():
            return release, version
        raise RuntimeError("Incomplete release exists; inspect it before retrying")
    release.mkdir()
    try:
        with tarfile.open(fileobj=io.BytesIO(git(base, "archive", version))) as archive:
            archive.extractall(release, filter="data")
        run(sys.executable, "-m", "venv", str(release / "venv"))
        python = release / "venv/bin/python"
        run(str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(release / "requirements.txt"))
        run(str(python), "-m", "pip", "check")
        run(str(python), "-m", "unittest", "discover", "-s", "tests", "-q", cwd=release, env=release_environment())
        for example in (release / "config").glob("*.example.json"):
            destination = base / "config" / example.name
            if not destination.exists():
                shutil.copy2(example, destination)
        shutil.rmtree(release / "config")
        (release / "config").symlink_to(base / "config", target_is_directory=True)
        (release / ".env").symlink_to(base / ".env")
        (release / ".release-sha").write_text(version + "\n")
        (release / ".prepared").write_text("tests and dependencies passed\n")
        if os.geteuid() == 0:
            owner = base.stat()
            for root, dirs, files in os.walk(release):
                for name in dirs + files:
                    os.chown(Path(root)/name, owner.st_uid, owner.st_gid, follow_symlinks=False)
            os.chown(release, owner.st_uid, owner.st_gid)
        return release, version
    except BaseException:
        # Keep the failed candidate available for inspection. Nothing live changed.
        print(f"Release preparation failed: {release}", file=sys.stderr)
        raise


def activate(base, release, version, service, *, unit_root=None, timeout=90):
    if not (release / ".prepared").is_file():
        raise RuntimeError("Release has not passed preparation")
    for secret in (base / ".env", base / "config/antarctic_tokens.json"):
        if secret.exists():
            os.chmod(secret, 0o600)
    directory = (unit_root or Path("/etc/systemd/system")) / (service + ".service.d")
    override = directory / "release.conf"
    previous = override.read_bytes() if override.exists() else None
    unit = f"""[Service]
WorkingDirectory={release}
ExecStart=
ExecStart={release}/venv/bin/python {release}/main.py
Environment=PYTHONDONTWRITEBYTECODE=1
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths={base}/config
RestrictSUIDSGID=yes
"""
    privileged("mkdir", "-p", str(directory))
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp)/"release.conf"
        source.write_text(unit)
        started = time.time()
        try:
            privileged("install", "-m", "644", str(source), str(override))
            privileged("systemctl", "daemon-reload")
            privileged("systemctl", "restart", service)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                pid = int(subprocess.check_output(["systemctl", "show", service, "-p", "MainPID", "--value"]))
                try:
                    health = json.loads((base / "config/health.json").read_text())
                    if pid and validate_health(health, version, pid, started):
                        print(f"Activated {version}; fresh source data and heartbeat verified")
                        return
                except (OSError, ValueError, TypeError):
                    pass
                time.sleep(2)
            raise RuntimeError("Candidate failed health checks")
        except BaseException:
            if previous is not None:
                source.write_bytes(previous)
                privileged("install", "-m", "644", str(source), str(override))
            else:
                privileged("rm", "-f", str(override))
            privileged("systemctl", "daemon-reload")
            privileged("systemctl", "restart", service)
            print("Previous service configuration restored", file=sys.stderr)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-dir", type=Path, default=Path("/opt/crypto-exkurs-bot"))
    parser.add_argument("--ref", default="@{upstream}")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--service", default="crypto-exkurs-bot")
    args = parser.parse_args()
    os.umask(0o022)  # Release code must remain readable by the service account.
    base = args.install_dir.resolve()
    release, version = prepare(base, args.ref)
    print(f"Prepared {version} at {release}")
    if not args.prepare_only:
        activate(base, release, version, args.service)


if __name__ == "__main__":
    main()
