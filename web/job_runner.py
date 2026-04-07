from __future__ import annotations

import threading
import traceback
import uuid
from copy import deepcopy
import sys
from pathlib import Path
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import common
from web.repository import jobs_path

_LOCK = threading.Lock()


def _load_jobs(client_slug: str) -> list[dict[str, Any]]:
    data = common.load_json_file(jobs_path(client_slug))
    if not isinstance(data, dict):
        return []
    items = data.get("items") or []
    return [item for item in items if isinstance(item, dict)]


def _save_jobs(client_slug: str, items: list[dict[str, Any]]) -> None:
    common.save_json_file(jobs_path(client_slug), {"items": items})


def _update_job(client_slug: str, job_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        items = _load_jobs(client_slug)
        for index, item in enumerate(items):
            if item.get("job_id") != job_id:
                continue
            updated = deepcopy(item)
            updated.update(patch)
            updated["updated_at"] = common.timestamp()
            items[index] = updated
            _save_jobs(client_slug, items)
            return updated
    raise KeyError(f"job not found: {job_id}")


def latest_job_for_task(client_slug: str, task_id: str) -> dict[str, Any] | None:
    items = _load_jobs(client_slug)
    for item in reversed(items):
        if item.get("task_id") == task_id:
            return deepcopy(item)
    return None


def start_job(
    client_slug: str,
    task_id: str,
    action: str,
    target: Callable[..., dict[str, Any]],
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    job = {
        "job_id": job_id,
        "task_id": task_id,
        "action": action,
        "status": "queued",
        "result": None,
        "error": None,
        "created_at": common.timestamp(),
        "updated_at": common.timestamp(),
    }
    with _LOCK:
        items = _load_jobs(client_slug)
        items.append(job)
        _save_jobs(client_slug, items)

    def runner() -> None:
        _update_job(client_slug, job_id, {"status": "running"})
        try:
            result = target(*args, **kwargs)
            _update_job(client_slug, job_id, {"status": "succeeded", "result": result})
        except Exception as exc:  # pragma: no cover - exercised by manual runs
            _update_job(
                client_slug,
                job_id,
                {
                    "status": "failed",
                    "error": f"{exc}\n{traceback.format_exc()}",
                },
            )

    thread = threading.Thread(target=runner, daemon=True, name=f"web-job-{job_id[:8]}")
    thread.start()
    return job
