"""Run the conformance scenarios against a locally started backend, including restart-restore.

    uv run --all-extras python tests/conformance/run.py fastapi
    uv run --all-extras python tests/conformance/run.py worker  # uv >= 0.13.4, web/dist built

Starts the server, runs every scenario, creates a mid-game room, restarts the server (rooms must
survive: FastAPI via PANDEMIC_DATA_DIR, the Worker via its local Durable Object storage), then
verifies the room. The server is stopped on exit.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (pandemic-conformance)"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(base: str, proc: subprocess.Popen, timeout: float = 120) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise SystemExit(f"server exited early with code {proc.returncode}")
        try:
            req = urllib.request.Request(base + "/meta", headers=UA)
            with urllib.request.urlopen(req, timeout=3) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise SystemExit("server did not become ready")


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("fastapi", "worker"):
        print(__doc__)
        return 2
    target = sys.argv[1]
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    tmp = tempfile.mkdtemp(prefix="pandemic-conf-")
    state_file = str(Path(tmp) / "state.json")
    env = dict(os.environ)
    if target == "fastapi":
        env["PANDEMIC_DATA_DIR"] = str(Path(tmp) / "rooms")
        cmd = [sys.executable, "-m", "pandemic.server", "--port", str(port)]
        cwd = ROOT
    else:
        subprocess.run([str(ROOT / "cloudflare/worker/scripts/sync.sh")], check=True)
        cmd = ["uv", "run", "pywrangler", "dev", "--port", str(port)]
        cwd = ROOT / "cloudflare/worker"
    conf = [sys.executable, str(HERE / "conformance.py"), "--base", base,
            "--state-file", state_file]

    def start() -> subprocess.Popen:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, start_new_session=True,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_ready(base, proc)
        return proc

    rc = 0
    proc = start()
    try:
        for phase in ("all", "restart-setup"):
            rc |= subprocess.run([*conf, "--phase", phase]).returncode
        print("-- restarting server --")
        stop(proc)
        proc = start()
        rc |= subprocess.run([*conf, "--phase", "restart-verify"]).returncode
    finally:
        stop(proc)
    print("ALL PASSED" if rc == 0 else "FAILURES")
    return rc


if __name__ == "__main__":
    sys.exit(main())
