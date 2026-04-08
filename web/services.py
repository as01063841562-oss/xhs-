from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import common
from web.repository import DEFAULT_ACCOUNT_KEY, create_task, get_task, list_tasks, update_task
from xhs_customer_router import route_message
from xhs_customer_state import load_state, materials_gate_path


def _load_runtime_snapshots(session_output_dir: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not session_output_dir:
        return None, None

    session_dir = common.resolve_path(session_output_dir)
    if not session_dir or not session_dir.exists():
        return None, None

    review_state = common.load_json_file(session_dir / "review_state.json")
    result = common.load_json_file(session_dir / "result.json")
    review_snapshot = review_state if isinstance(review_state, dict) else None
    result_snapshot = result if isinstance(result, dict) else None
    return review_snapshot, result_snapshot


def build_action_message(task: dict[str, Any], action: str, payload: dict[str, Any]) -> str:
    if action == "generate-topic":
        return f"#选题 {task['topic']}"
    if action == "generate-cover":
        return "生成封面图"
    if action == "generate-graphics":
        return "生成配图"
    if action == "confirm-current":
        current_state = task.get("current_state")
        if current_state == "state_1_copywriting":
            return "这个文案可以，继续"
        if current_state == "state_2_cover":
            return "这张封面图可以，继续"
        if current_state == "state_3_graphics":
            return "这组配图可以，继续"
        return "确认"
    if action == "select-topic":
        return str(payload.get("topic_title") or "")
    if action == "request-change":
        return str(payload.get("message") or "")
    raise ValueError(f"unsupported action: {action}")


def sync_task_from_runtime(client_slug: str, task: dict[str, Any]) -> dict[str, Any]:
    synced = deepcopy(task)
    synced["account_key"] = str(synced.get("account_key") or DEFAULT_ACCOUNT_KEY)
    state = load_state(client_slug, task["open_id"])
    synced["current_state"] = state.get("current_state", synced.get("current_state"))
    synced["materials_ready"] = state.get("materials_ready", synced.get("materials_ready"))
    synced["session_output_dir"] = state.get("session_output_dir")
    synced["confirmed"] = state.get("confirmed", {})
    synced["drafts"] = state.get("drafts", {})

    session_output_dir = state.get("session_output_dir")
    review_state, result = _load_runtime_snapshots(session_output_dir)
    if isinstance(review_state, dict):
        synced["review_message_id"] = review_state.get("current_review_message_id")
        synced["review_status"] = review_state.get("status")
    if isinstance(result, dict):
        synced["runtime_status"] = result.get("status")
    synced["status"] = synced.get("runtime_status") or synced.get("review_status") or synced.get("status") or "idle"
    return synced


def create_web_task(
    client_slug: str,
    title: str,
    topic: str,
    audience: str,
    created_by_role: str,
    account_key: str = DEFAULT_ACCOUNT_KEY,
) -> dict[str, Any]:
    task = create_task(client_slug, title, topic, audience, created_by_role, account_key=account_key)
    return sync_task_from_runtime(client_slug, task)


def list_synced_tasks(client_slug: str, account_key: str | None = None) -> list[dict[str, Any]]:
    return [sync_task_from_runtime(client_slug, task) for task in list_tasks(client_slug, account_key=account_key)]


def set_materials_gate(client_slug: str, materials_ready: bool) -> dict[str, Any]:
    current = common.load_json_file(materials_gate_path(client_slug))
    if not isinstance(current, dict):
        current = {}
    current["materials_ready"] = bool(materials_ready)
    current["updated_at"] = common.timestamp()
    common.save_json_file(materials_gate_path(client_slug), current)
    return current


def run_task_action(
    client_slug: str,
    task_id: str,
    action: str,
    payload: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    payload = payload or {}
    task = get_task(client_slug, task_id)

    if action == "sync":
        synced = sync_task_from_runtime(client_slug, task)
        update_task(
            client_slug,
            task_id,
            {
                "current_state": synced.get("current_state"),
                "materials_ready": synced.get("materials_ready"),
                "session_output_dir": synced.get("session_output_dir"),
                "review_message_id": synced.get("review_message_id"),
                "review_status": synced.get("review_status"),
                "runtime_status": synced.get("runtime_status"),
                "status": synced.get("status"),
                "account_key": synced.get("account_key"),
            },
        )
        return {"status": "ok", "action": "sync", "task": synced}

    if action == "request-change":
        updated = update_task(
            client_slug,
            task_id,
            {
                "client_change_request": str(payload.get("message") or "").strip(),
                "status": "needs_ops",
                "account_key": task.get("account_key") or DEFAULT_ACCOUNT_KEY,
            },
        )
        return {"status": "ok", "action": "request-change", "task": updated}

    message = build_action_message(task, action, payload)
    result = route_message(
        client_slug=client_slug,
        open_id=task["open_id"],
        message=message,
        dry_run=dry_run,
        audience=task.get("audience") or "武汉家长",
    )
    synced = sync_task_from_runtime(client_slug, task)
    update_patch = {
        "current_state": synced.get("current_state"),
        "materials_ready": synced.get("materials_ready"),
        "session_output_dir": synced.get("session_output_dir"),
        "review_message_id": synced.get("review_message_id"),
        "review_status": synced.get("review_status"),
        "runtime_status": synced.get("runtime_status"),
        "status": result.get("status", "idle"),
        "account_key": synced.get("account_key"),
    }
    if result.get("status") == "blocked":
        update_patch["last_error"] = result.get("reason")
    updated = update_task(client_slug, task_id, update_patch)
    return {"status": result.get("status", "ok"), "action": action, "result": result, "task": sync_task_from_runtime(client_slug, updated)}
