"""Small load test of a deployment: mixed read pages and draft previews (no database writes), fixed concurrency.

    python scripts/loadtest.py [--base https://legal-agreement-ai.vercel.app] [--n 150] [--concurrency 10]
Writes eval/results/deployed/loadtest.json. Keep it modest on free tiers.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import random
import statistics
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://legal-agreement-ai.vercel.app")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--concurrency", type=int, default=10)
    a = ap.parse_args()
    items = [json.loads(line) for line in (ROOT / "data" / "synthetic" / "intake.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    rng = random.Random(5)
    jobs = []
    for i in range(a.n):
        if i % 3 == 0:
            it = rng.choice(items)
            jobs.append(("POST /api/v1/draft/preview", dict(agreement_type=it["agreement_type"], form={k: v for k, v in it["form"].items() if k != "agreement_type"},
                                                             text=it["text"])))
        else:
            jobs.append((rng.choice(["GET /", "GET /queue", "GET /scoreboard", "GET /api/v1/requests"]), None))
    session = requests.Session()

    def run(job):
        name, body = job
        method, path = name.split(" ", 1)
        t0 = time.time()
        try:
            r = session.request(method, a.base + path, json=body, timeout=60, headers={"x-forwarded-for": f"10.0.0.{rng.randint(1, 250)}"})
            return name, r.status_code, time.time() - t0
        except requests.RequestException:
            return name, 0, time.time() - t0

    t0 = time.time()
    with cf.ThreadPoolExecutor(a.concurrency) as ex:
        results = list(ex.map(run, jobs))
    wall = time.time() - t0
    out = {"base": a.base, "requests": a.n, "concurrency": a.concurrency, "wall_s": round(wall, 1), "throughput_rps": round(a.n / wall, 2), "by_endpoint": {}}
    for name in sorted({r[0] for r in results}):
        lat = sorted(r[2] for r in results if r[0] == name)
        codes = [r[1] for r in results if r[0] == name]
        out["by_endpoint"][name] = dict(n=len(lat), status_codes={str(c): codes.count(c) for c in sorted(set(codes))}, errors=sum(1 for c in codes if c == 0 or c >= 500), non_2xx=sum(1 for c in codes if not 200 <= c < 300),
                                        p50_ms=round(1000 * statistics.median(lat)), p95_ms=round(1000 * lat[min(len(lat) - 1, int(0.95 * len(lat)))]),
                                        max_ms=round(1000 * lat[-1]))
    path = ROOT / "eval" / "results" / "deployed" / "loadtest.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
