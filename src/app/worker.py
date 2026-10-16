"""Queue worker (production "queue" mode): claims drafting jobs from Postgres (SELECT ... FOR UPDATE SKIP LOCKED in
worker_claim()), runs the drafting engine and stores the draft with worker_complete(). Stateless and horizontally
scalable; Kubernetes scales it on queue depth. A job is retried up to 3 times; a lock older than 5 minutes is reclaimed.

    python -m src.app.worker
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

from src.app.config import settings
from src.app.main import llm, search, store

log = logging.getLogger("worker")
_stop = False
HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT", "/tmp/worker.heartbeat"))


def beat() -> None:
    """Liveness signal for Docker / Kubernetes: the probe fails if this file is older than 60 s."""
    try:
        HEARTBEAT.write_text(str(time.time()))
    except OSError:
        pass


def healthy(max_age: float = 60.0) -> bool:
    try:
        return time.time() - float(HEARTBEAT.read_text()) < max_age
    except (OSError, ValueError):
        return False


def _sigterm(*_):
    global _stop
    _stop = True


def run_once() -> bool:
    from src.drafting.engine import make_draft
    st = store()
    job = st.worker_claim()
    if not job:
        return False
    t0 = time.time()
    try:
        mode = settings().effective_mode
        model = llm() if mode != "rules" else None
        draft = make_draft(job["agreement_type"], {k: v for k, v in (job.get("form") or {}).items()}, job.get("text") or "", search(),
                           mode=mode if model is not None or mode == "rules" else "rules", llm=model)
        st.worker_complete(dict(job_id=job["job_id"], request_id=job["request_id"], draft=draft))
        log.info(json.dumps(dict(event="job_done", job=job["job_id"], route=draft["route"], seconds=round(time.time() - t0, 2))))
    except Exception as e:  # noqa: BLE001
        log.exception(json.dumps(dict(event="job_failed", job=job["job_id"])))
        st.worker_complete(dict(job_id=job["job_id"], request_id=job["request_id"], error=f"{type(e).__name__}: {e}"[:500]))
    return True


def main() -> None:
    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)
    if settings().store != "postgres":
        raise SystemExit("the queue worker needs STORE=postgres")
    log.info(json.dumps(dict(event="worker_start", mode=settings().effective_mode)))
    idle, backoff = 0.5, 1.0
    while not _stop:
        beat()
        try:
            worked = run_once()
            backoff = 1.0
        except Exception as e:  # noqa: BLE001  database not migrated yet, network blip: retry, never crash-loop
            log.warning(json.dumps(dict(event="worker_retry", error=f"{type(e).__name__}: {str(e)[:200]}", sleep_s=backoff)))
            time.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
            continue
        if worked:
            idle = 0.5
        else:
            time.sleep(idle)
            idle = min(idle * 2, 5.0)
    log.info(json.dumps(dict(event="worker_stop")))


if __name__ == "__main__":
    if sys.argv[1:] == ["--healthcheck"]:
        sys.exit(0 if healthy() else 1)
    main()
