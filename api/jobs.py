"""Background jobs for a workspace (item 24 step 3): an ingest or "load the demo company" runs in a thread
inside the request's workspace context, and its progress (documents, facts, disputes) is polled."""
from __future__ import annotations

import contextvars
import threading
import uuid
from typing import Callable

JOBS: dict[str, dict] = {}
MAX_KEPT = 200


def start(workspace: str, kind: str, fn: Callable[[dict], None]) -> dict:
    job = {"id": uuid.uuid4().hex[:12], "workspace": workspace, "kind": kind, "state": "running",
           "docs": 0, "total": 0, "facts": 0, "disputes": 0, "error": ""}
    JOBS[job["id"]] = job
    while len(JOBS) > MAX_KEPT:
        JOBS.pop(next(iter(JOBS)))
    ctx = contextvars.copy_context()   # the thread keeps the request's workspace

    def run() -> None:
        try:
            fn(job)
            job["state"] = "done"
        except Exception as e:  # noqa: BLE001 - reported to the person, not raised
            job["state"], job["error"] = "failed", str(e)
    threading.Thread(target=lambda: ctx.run(run), daemon=True).start()
    return job


def get(job_id: str, workspace: str) -> dict | None:
    j = JOBS.get(job_id)
    return j if j and j["workspace"] == workspace else None
