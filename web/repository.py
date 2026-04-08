from __future__ import annotations

import secrets
import sys
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import common
from xhs_customer_state import default_state, save_state

DEFAULT_ACCOUNT_KEY = "primary"


def _web_state_dir(client_slug: str):
    return common.ensure_dir(common.get_client_root(client_slug) / "state")


def tasks_path(client_slug: str):
    return _web_state_dir(client_slug) / "web_tasks.json"


def access_path(client_slug: str):
    return _web_state_dir(client_slug) / "web_access.json"


def jobs_path(client_slug: str):
    return _web_state_dir(client_slug) / "web_jobs.json"


def _load_list(path) -> list[dict[str, Any]]:
    data = common.load_json_file(path)
    if not isinstance(data, dict):
        return []
    items = data.get("items") or []
    return [item for item in items if isinstance(item, dict)]


def _save_list(path, items: list[dict[str, Any]]) -> None:
    common.save_json_file(path, {"items": items})


def ensure_access_config(client_slug: str) -> dict[str, str]:
    path = access_path(client_slug)
    data = common.load_json_file(path)
    if not isinstance(data, dict):
        data = {}

    changed = False
    for key in ("secret_key", "ops_token", "client_token"):
        if not data.get(key):
            data[key] = secrets.token_urlsafe(24)
            changed = True
    if changed or not path.exists():
        common.save_json_file(path, data)
    return {
        "secret_key": str(data["secret_key"]),
        "ops_token": str(data["ops_token"]),
        "client_token": str(data["client_token"]),
    }


def _new_task_record(
    client_slug: str,
    title: str,
    topic: str,
    audience: str,
    created_by_role: str,
    account_key: str = DEFAULT_ACCOUNT_KEY,
) -> dict[str, Any]:
    task_id = uuid.uuid4().hex
    open_id = f"web_task_{task_id[:12]}"
    account_key = str(account_key or DEFAULT_ACCOUNT_KEY)
    return {
        "task_id": task_id,
        "client_slug": client_slug,
        "account_key": account_key,
        "title": title,
        "topic": topic,
        "audience": audience,
        "created_by_role": created_by_role,
        "open_id": open_id,
        "current_state": "state_0_topic",
        "materials_ready": False,
        "status": "idle",
        "review_message_id": None,
        "session_output_dir": None,
        "client_change_request": None,
        "last_error": None,
        "created_at": common.timestamp(),
        "updated_at": common.timestamp(),
    }


def list_tasks(client_slug: str) -> list[dict[str, Any]]:
    items = _load_list(tasks_path(client_slug))
    return list(reversed(items))


def get_task(client_slug: str, task_id: str) -> dict[str, Any]:
    for item in _load_list(tasks_path(client_slug)):
        if item.get("task_id") == task_id:
            return deepcopy(item)
    raise KeyError(f"task not found: {task_id}")


def create_task(
    client_slug: str,
    title: str,
    topic: str,
    audience: str,
    created_by_role: str,
    account_key: str = DEFAULT_ACCOUNT_KEY,
) -> dict[str, Any]:
    items = _load_list(tasks_path(client_slug))
    task = _new_task_record(client_slug, title, topic, audience, created_by_role, account_key=account_key)
    items.append(task)
    _save_list(tasks_path(client_slug), items)
    save_state(client_slug, task["open_id"], default_state())
    return deepcopy(task)


def update_task(client_slug: str, task_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    items = _load_list(tasks_path(client_slug))
    for index, item in enumerate(items):
        if item.get("task_id") != task_id:
            continue
        updated = deepcopy(item)
        updated.update(patch)
        updated["updated_at"] = common.timestamp()
        items[index] = updated
        _save_list(tasks_path(client_slug), items)
        return deepcopy(updated)
    raise KeyError(f"task not found: {task_id}")
