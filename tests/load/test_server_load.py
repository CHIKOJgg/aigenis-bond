"""Server load / stress test: prove the API server sustains real traffic.

This is the server-load half of the brief — verify the *running server*
withstands realistic concurrent load without crashing or degrading.

Approach
--------
* Create a shared file-based SQLite DB and the schema (so the server has real
  tables to query — production uses Alembic; the suite creates them directly).
* Boot the real FastAPI app on a TCP port via a ``uvicorn`` subprocess, pointed
  at that same DB file, so the full ASGI stack (CORS, rate-limit, feature-gating,
  DB pool) runs exactly as in production on a real socket.
* Fire a large burst of mixed requests from many worker threads concurrently.
* Assert every request succeeded (no 5xx / connection errors) and that the
  per-request latency stayed within a sane ceiling — i.e. the server held up.

For a richer, scenario-driven Locust run, use ``tests/load/locustfile.py``:

    locust -f tests/load/locustfile.py --host http://localhost:8000 \\
           --users 50 --spawn-rate 10 --run-time 1m --headless

Env tunables: LOAD_USERS (threads, 40), LOAD_REQUESTS_PER_USER (25),
LOAD_PORT (8731), LOAD_MAX_MS (per-request ceiling, 5000),
LOAD_MAX_FAILURE_RATE (0.0).
"""
from __future__ import annotations

import concurrent.futures
import os
import subprocess
import sys
import time

import httpx
import pytest

HOST = "127.0.0.1"
PORT = int(os.getenv("LOAD_PORT", "8731"))
BASE_URL = f"http://{HOST}:{PORT}"


def _wait_for_port(timeout: float = 40.0) -> None:
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("uvicorn server did not become ready in time")


@pytest.mark.load
def test_server_withstands_concurrent_load(tmp_path):
    users = int(os.getenv("LOAD_USERS", "40"))
    per_user = int(os.getenv("LOAD_REQUESTS_PER_USER", "25"))
    max_ms = float(os.getenv("LOAD_MAX_MS", "5000"))
    max_failure_rate = float(os.getenv("LOAD_MAX_FAILURE_RATE", "0.0"))

    # Use a shared FILE-based sqlite so the test process can create the schema
    # and the server subprocess queries the very same tables.
    db_file = tmp_path / "load_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    db_url_sync = f"sqlite:///{db_file}"

    # Create the schema in this process (same file the server will use).
    import asyncio

    from scraper.db import get_engine
    from scraper.orm import Base

    async def _schema():
        from sqlalchemy.ext.asyncio import create_async_engine

        eng = create_async_engine(db_url)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await eng.dispose()

    asyncio.run(_schema())

    anon_paths = [
        "/health",
        "/api/v1/bonds?limit=20",
        "/api/v1/stats",
        "/api/v1/top?limit=10",
        "/api/v1/subscribe-info",
    ]

    server_env = dict(os.environ)
    # Point the server at the SAME file-based DB and disable the rate limiter so
    # we measure SERVER capacity (rate-limiting is covered in
    # tests/test_rate_limit_load.py).
    server_env["DATABASE_URL"] = db_url
    server_env["DATABASE_URL_SYNC"] = db_url_sync
    server_env["RATE_LIMIT_BACKEND"] = "memory"
    server_env["API_RATE_LIMIT"] = os.getenv("LOAD_RATE_LIMIT", "100000")
    server_env["API_RATE_WINDOW"] = "60"

    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "api.main:app",
            "--host", HOST,
            "--port", str(PORT),
            "--log-level", "error",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=server_env,
    )
    try:
        _wait_for_port()

        from api.auth.service import create_access_token

        auth_headers = {"Authorization": f"Bearer {create_access_token(1)}"}

        def fire_one(idx: int) -> tuple[int, float, str]:
            path = anon_paths[idx % len(anon_paths)]
            headers = auth_headers if path.startswith("/api/v1/portfolio") else None
            start = time.monotonic()
            try:
                with httpx.Client(timeout=10.0, headers=headers) as c:
                    resp = c.get(BASE_URL + path)
                dt_ms = (time.monotonic() - start) * 1000
                return resp.status_code, dt_ms, path
            except Exception as exc:  # connection error / timeout
                return -1, (time.monotonic() - start) * 1000, f"ERR:{exc}"

        tasks = users * per_user
        results: list[tuple[int, float, str]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=users) as ex:
            futs = [ex.submit(fire_one, i) for i in range(tasks)]
            for f in concurrent.futures.as_completed(futs):
                results.append(f.result())

        ok = sum(1 for s, _, _ in results if s == 200)
        failures = [r for r in results if r[0] != 200]
        failure_rate = len(failures) / len(results) if results else 1.0
        max_latency = max((dt for _, dt, _ in results), default=0.0)
        avg_latency = sum(dt for _, dt, _ in results) / len(results) if results else 0.0

        print(
            f"\n[load] tasks={tasks} ok={ok} failures={len(failures)} "
            f"failure_rate={failure_rate:.4f} "
            f"avg_ms={avg_latency:.1f} max_ms={max_latency:.1f}"
        )
        if failures:
            from collections import Counter

            print("  sample failures:", Counter(f[2] for f in failures).most_common(5))

        assert results, "no requests were issued"
        assert failure_rate <= max_failure_rate, (
            f"failure rate {failure_rate:.4f} exceeded threshold {max_failure_rate} "
            f"({len(failures)}/{len(results)} failed)"
        )
        assert max_latency <= max_ms, (
            f"worst request latency {max_latency:.1f}ms exceeded ceiling {max_ms}ms"
        )
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-m", "load"]))
