"""Performance smoke test — SC-001: p95 < 500ms under 100 concurrent requests.

Run: python tests/perf/smoke_test.py

Requires a running backend at http://localhost:8000.
"""
from __future__ import annotations

import asyncio
import statistics
import time
import uuid
from datetime import datetime, timezone

import httpx


BASE_URL = "http://localhost:8000"
CONCURRENT = 100
ENDPOINT = "/api/v1/leads/capture"
TARGET_P95_MS = 500


def _payload(i: int) -> dict:
    return {
        "contact": {
            "nome": f"Test User {i}",
            "azienda": f"TestCo {i}",
            "email": f"perf.test.{i}.{uuid.uuid4().hex[:6]}@testco.it",
        },
        "qualification": {
            "target": "azienda",
            "obiettivo": "due_diligence",
            "geografia": "Europa",
            "role": "legal",
        },
        "events": [
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "session.started",
                "event_payload": {},
                "sequence_number": 0,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "locale": "it",
            }
        ],
        "locale": "it",
        "idempotency_key": str(uuid.uuid4()),
    }


async def _send_one(client: httpx.AsyncClient, i: int) -> float:
    start = time.perf_counter()
    try:
        resp = await client.post(ENDPOINT, json=_payload(i), timeout=10.0)
        if resp.status_code not in (200, 429):
            print(f"  ⚠ Unexpected status {resp.status_code} for request {i}")
    except Exception as exc:
        print(f"  ✗ Request {i} failed: {exc}")
    elapsed_ms = (time.perf_counter() - start) * 1000
    return elapsed_ms


async def run_smoke_test() -> None:
    print(f"\nDeepSearch Backend Performance Smoke Test")
    print(f"Endpoint: {BASE_URL}{ENDPOINT}")
    print(f"Concurrent requests: {CONCURRENT}")
    print(f"Target p95: < {TARGET_P95_MS}ms")
    print("-" * 50)

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        tasks = [_send_one(client, i) for i in range(CONCURRENT)]
        wall_start = time.perf_counter()
        durations = await asyncio.gather(*tasks)
        wall_elapsed = (time.perf_counter() - wall_start) * 1000

    durations_sorted = sorted(durations)
    p50 = statistics.median(durations_sorted)
    p95_idx = int(len(durations_sorted) * 0.95)
    p99_idx = int(len(durations_sorted) * 0.99)
    p95 = durations_sorted[min(p95_idx, len(durations_sorted) - 1)]
    p99 = durations_sorted[min(p99_idx, len(durations_sorted) - 1)]
    min_t = min(durations_sorted)
    max_t = max(durations_sorted)

    print(f"\nResults ({CONCURRENT} requests):")
    print(f"  Min:     {min_t:.1f}ms")
    print(f"  p50:     {p50:.1f}ms")
    print(f"  p95:     {p95:.1f}ms  {'✓ PASS' if p95 < TARGET_P95_MS else '✗ FAIL'}")
    print(f"  p99:     {p99:.1f}ms")
    print(f"  Max:     {max_t:.1f}ms")
    print(f"  Total wall time: {wall_elapsed:.0f}ms")
    print(f"  Throughput: {CONCURRENT / (wall_elapsed / 1000):.1f} req/s")

    if p95 < TARGET_P95_MS:
        print(f"\n✓ SC-001 PASS: p95 ({p95:.0f}ms) < {TARGET_P95_MS}ms target")
    else:
        print(f"\n✗ SC-001 FAIL: p95 ({p95:.0f}ms) >= {TARGET_P95_MS}ms target")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(run_smoke_test())
