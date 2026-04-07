#!/usr/bin/env python3
"""Customer state helpers for the XHS workflow."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import common

DEFAULT_CURRENT_STATE = "state_0_topic"
COPYWRITING_STATE = "state_1_copywriting"


def _state_template() -> dict[str, Any]:
    return {
        "materials_ready": False,
        "current_state": DEFAULT_CURRENT_STATE,
        "current_topic_id": None,
        "confirmed": {
            "topic": None,
            "title": None,
            "copywriting": None,
            "cover": None,
            "graphics": None,
        },
        "drafts": {
            "topics": [],
            "copywriting": None,
            "cover_images": [],
            "graphic_images": [],
        },
        "last_revision_scope": None,
        "last_user_intent": None,
        "session_output_dir": None,
        "updated_at": "",
    }


def default_state() -> dict[str, Any]:
    return deepcopy(_state_template())


def _state_file_path(client_slug: str, open_id: str) -> Path:
    return common.get_client_root(client_slug) / "state" / "feishu_dm" / f"{open_id}.json"


def state_path(client_slug: str, open_id: str) -> Path:
    return _state_file_path(client_slug, open_id)


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    return common.deep_merge(default_state(), state)


def load_state(client_slug: str, open_id: str) -> dict[str, Any]:
    data = common.load_json_file(_state_file_path(client_slug, open_id))
    if not isinstance(data, dict) or not data:
        return default_state()
    return _normalize_state(data)


def save_state(client_slug: str, open_id: str, state: dict[str, Any]) -> Path:
    """Mutate `state` in place, stamp `updated_at`, then persist it."""
    state["updated_at"] = common.timestamp()
    return common.save_json_file(_state_file_path(client_slug, open_id), state)


def ensure_session_dir(client_slug: str, open_id: str, state: dict[str, Any]) -> Path:
    """Mutate `state` in place and return the active session directory."""
    existing_session_dir = state.get("session_output_dir")
    if existing_session_dir:
        existing_path = Path(existing_session_dir)
        if existing_path.exists():
            return existing_path

    session_dir = common.ensure_dir(
        common.get_client_session_dir(client_slug) / f"{open_id}-{common.timestamp()}"
    )
    state["session_output_dir"] = str(session_dir)
    return session_dir


def reset_after_copywriting(state: dict[str, Any]) -> dict[str, Any]:
    """Mutate `state` in place and roll it back to copywriting stage."""
    topic = state.setdefault("confirmed", {}).get("topic")
    current_topic_id = state.get("current_topic_id")

    state.update(
        {
            "current_state": COPYWRITING_STATE,
            "current_topic_id": current_topic_id,
            "confirmed": {
                "topic": topic,
                "title": None,
                "copywriting": None,
                "cover": None,
                "graphics": None,
            },
            "drafts": {
                "topics": [],
                "copywriting": None,
                "cover_images": [],
                "graphic_images": [],
            },
        }
    )
    return state
