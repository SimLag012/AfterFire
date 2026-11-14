"""Run AfterFire locally, without Docker. Stop all services with Ctrl+C."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--web-port", type=int, default=3000)
    parser.add_argument("--check", action="store_true", help="Verify startup and stop all services.")
    args = parser.parse_args()
    if args.api_port == args.web_port:
        parser.error("API and frontend need different ports.")
    for port in (args.api_port, args.web_port):
        if not 1 <= port <= 65535:
            parser.error("Ports must be between 1 and 65535.")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))

    backend = ROOT / "backend"
    executable = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    python = next((str(path) for path in (
        backend / ".venv-windows" / executable,
        backend / ".venv" / executable,
    ) if path.is_file()), sys.executable)
    node = shutil.which("node")
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    if not node or not vite.is_file():
        raise SystemExit("Install Node.js and run npm ci in frontend first.")

    # Read credentials without shell wrappers so shutdown reaches each service.
    from dotenv import dotenv_values
    env = {
        **{k: v for k, v in dotenv_values(backend / ".env").items() if v is not None},
        **{k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None},
        **os.environ,
    }
    # A Docker DATABASE_URL refers to host 'db', which does not exist locally.
    env["DATABASE_URL"] = "sqlite+aiosqlite:///" + (backend / "afterfire.db").as_posix()
    runtime = ROOT / ".local-runtime"
    runtime.mkdir(exist_ok=True)
    env["AFTERFIRE_ANALYSIS_CACHE_DIR"] = str(runtime / "analysis-cache")
    env["AF_API_PROXY_URL"] = f"http://127.0.0.1:{args.api_port}"
    env["PYTHONUNBUFFERED"] = "1"
    processes = []
    logs = []

    def start(name, argv, cwd):
        log = (runtime / f"{name}.log").open("w", encoding="utf-8")
        logs.append(log)
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log,
                                   stderr=subprocess.STDOUT)
        processes.append((name, process))
        return process

    def wait_ready(url, process, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Service exited; see {runtime}")
            try:
                with urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        return
            except (URLError, TimeoutError, OSError):
                pass
            time.sleep(0.5)
        raise RuntimeError(f"Startup timed out: {url}; see {runtime}")

    try:
        api = start("backend", [
            python, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(args.api_port),
        ], backend)
        wait_ready(f"http://127.0.0.1:{args.api_port}/openapi.json", api)
        # Start after schema initialization to avoid concurrent SQLite DDL.
        start("worker", [python, "-m", "app.jobs.analysis_worker"], backend)
        web = start("frontend", [
            node, str(vite), "--host", "127.0.0.1",
            "--port", str(args.web_port), "--strictPort",
        ], ROOT / "frontend")
        wait_ready(f"http://127.0.0.1:{args.web_port}", web)
        print(f"AfterFire: http://127.0.0.1:{args.web_port}", flush=True)
        print(f"API: http://127.0.0.1:{args.api_port}/docs", flush=True)
        print(f"SQLite: {backend / 'afterfire.db'}", flush=True)
        print(f"Logs: {runtime}\nCtrl+C stops all three services.", flush=True)
        if args.check:
            time.sleep(3)
            for name, process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f"{name} exited; see {runtime}")
            health_url = f"http://127.0.0.1:{args.web_port}/api/v1/health?probe=false"
            wait_ready(health_url, web, timeout=120)
            with urlopen(health_url, timeout=20) as response:
                if json.load(response).get("status") != "ok":
                    raise RuntimeError("API health check through frontend failed.")
            print("PASS: frontend, API proxy and analysis worker; shutting down.", flush=True)
            return
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f"{name} exited ({process.returncode}); see {runtime / (name + '.log')}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping AfterFire...", flush=True)
    finally:
        for _, process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for _, process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
