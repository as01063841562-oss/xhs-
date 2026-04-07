#!/usr/bin/env python3
"""Intent routing helpers for the XHS customer flow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import common
from xhs_feedback_parser import parse_feedback
from xhs_customer_state import ensure_session_dir, load_state, save_state
from xhs_feishu_flow import generate_slide_images, generate_xhs_payload

_TOPIC_HINTS = ("中考", "学科", "押题", "知识点")
_FEEDBACK_HINTS = ("修改", "换一个", "换个", "回到文案", "重新来", "汇总")
TOPIC_STATE = "state_0_topic"
COPYWRITING_STATE = "state_1_copywriting"
COVER_STATE = "state_2_cover"
GRAPHIC_STATE = "state_3_graphics"
DEFAULT_AUDIENCE = "武汉家长"
_MINIMAL_PNG = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
    "0000000D49444154789C63F8FFFFFF7F0009FB03FD2A86E38A0000000049454E44AE426082"
)


def _jsonish(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    return json.dumps(value, ensure_ascii=False)


def build_state_summary(state: dict[str, Any]) -> str:
    confirmed = state.get("confirmed") or {}
    locked_sections = [
        key
        for key in ("topic", "title", "copywriting", "cover", "graphics")
        if confirmed.get(key) is not None
    ]
    lines = [
        "当前会话摘要：",
        f"- materials_ready: {_jsonish(state.get('materials_ready'))}",
        f"- current_state: {state.get('current_state')}",
        f"- confirmed.topic: {confirmed.get('topic')}",
        f"- confirmed.title: {confirmed.get('title')}",
        f"- confirmed.copywriting: {confirmed.get('copywriting')}",
        f"- confirmed.cover: {confirmed.get('cover')}",
        f"- confirmed.graphics: {confirmed.get('graphics')}",
        f"- locked_sections: {json.dumps(locked_sections, ensure_ascii=False)}",
    ]
    current_revision_scope = state.get("last_revision_scope")
    if current_revision_scope is not None:
        lines.append(f"- current_revision_scope: {_jsonish(current_revision_scope)}")
    return "\n".join(lines)


def classify_message(message: str, state: dict[str, Any]) -> dict[str, Any]:
    text = (message or "").strip()

    if any(hint in text for hint in _FEEDBACK_HINTS):
        return {
            "intent": "feedback_request",
            "feedback": parse_feedback(text, state.get("current_state", "")),
        }

    if "封面图" in text or "生成封面图" in text:
        return {"intent": "cover_request"}

    if "配图" in text or "生成配图" in text:
        return {"intent": "graphic_request"}

    if (
        "#选题" in text
        or any(hint in text for hint in _TOPIC_HINTS)
    ):
        return {"intent": "topic_request"}

    return {"intent": "selection_or_confirmation"}


def guard_materials_ready(state: dict[str, Any], intent: str) -> dict[str, Any]:
    blocked_intents = {
        "topic_request",
        "selection_or_confirmation",
        "cover_request",
        "graphic_request",
    }
    if not state.get("materials_ready") and intent in blocked_intents:
        return {
            "allowed": False,
            "reason": "materials_not_ready",
            "intent": intent,
        }
    return {"allowed": True, "intent": intent}


def generate_copywriting_draft(
    topic: str,
    audience: str,
    config: dict[str, Any],
    state: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    payload = generate_xhs_payload(topic, audience, config, dry_run=dry_run)
    drafts = state.setdefault("drafts", {})
    drafts["copywriting"] = payload
    state["current_state"] = COPYWRITING_STATE
    return payload


def generate_cover_draft(
    run_dir: Path,
    payload: dict[str, Any],
    config: dict[str, Any],
    state: dict[str, Any],
    dry_run: bool = False,
    skip_image: bool = False,
) -> list[str]:
    images = generate_slide_images(
        run_dir=run_dir,
        payload=payload,
        topic_data=None,
        config=config,
        dry_run=dry_run,
        skip_image=skip_image,
    )
    cover_images = [str(path) for path in images]
    state.setdefault("drafts", {})["cover_images"] = cover_images
    state["current_state"] = COVER_STATE
    return cover_images


def _write_placeholder_png(path: Path) -> None:
    common.ensure_dir(path.parent)
    path.write_bytes(_MINIMAL_PNG)


def generate_graphic_draft(
    payload: dict[str, Any],
    state: dict[str, Any],
    run_dir: Path,
    count: int = 3,
) -> list[str]:
    graphic_dir = common.ensure_dir(run_dir / "graphics")
    generated: list[str] = []
    for index in range(1, count + 1):
        target = graphic_dir / f"graphic_{index}.png"
        _write_placeholder_png(target)
        generated.append(str(target))
    state.setdefault("drafts", {})["graphic_images"] = generated
    state["current_state"] = GRAPHIC_STATE
    return generated


def confirm_copywriting(state: dict[str, Any]) -> dict[str, Any]:
    drafts = state.setdefault("drafts", {})
    confirmed = state.setdefault("confirmed", {})
    confirmed["copywriting"] = drafts.get("copywriting")
    confirmed["cover"] = None
    confirmed["graphics"] = None
    state["current_state"] = COVER_STATE
    drafts["cover_images"] = []
    drafts["graphic_images"] = []
    return state


def route_message(
    client_slug: str,
    open_id: str,
    message: str,
    dry_run: bool = False,
    config_path: str | None = None,
    audience: str = DEFAULT_AUDIENCE,
) -> dict[str, Any]:
    state = load_state(client_slug, open_id)
    classified = classify_message(message, state)

    if classified["intent"] == "feedback_request":
        feedback = classified["feedback"]
        if feedback.get("operation") == "summary":
            return {
                "status": "ok",
                "intent": classified["intent"],
                "operation": "summary",
                "response": build_state_summary(state),
                "state_changed": False,
            }

    gate = guard_materials_ready(state, classified["intent"])
    if not gate["allowed"]:
        return {
            "status": "blocked",
            "intent": classified["intent"],
            "reason": gate["reason"],
            "response": "materials_not_ready",
            "state_changed": False,
        }

    state_changed = False
    result: dict[str, Any] = {
        "status": "ok",
        "intent": classified["intent"],
        "state_changed": False,
    }

    if (
        classified["intent"] == "selection_or_confirmation"
        and state.get("current_state") == COPYWRITING_STATE
        and state.get("confirmed", {}).get("topic")
    ):
        config = {} if dry_run else common.load_config(config_path)
        payload = generate_copywriting_draft(
            topic=str(state["confirmed"]["topic"]),
            audience=audience,
            config=config,
            state=state,
            dry_run=dry_run,
        )
        result["action"] = "generate_copywriting_draft"
        result["payload"] = payload
        state_changed = True
    elif (
        classified["intent"] == "cover_request"
        and state.get("drafts", {}).get("copywriting")
    ):
        config = {} if dry_run else common.load_config(config_path)
        run_dir = ensure_session_dir(client_slug, open_id, state)
        cover_images = generate_cover_draft(
            run_dir=run_dir,
            payload=state["drafts"]["copywriting"],
            config=config,
            state=state,
            dry_run=dry_run,
        )
        result["action"] = "generate_cover_draft"
        result["cover_images"] = cover_images
        state_changed = True
    elif (
        classified["intent"] == "graphic_request"
        and state.get("drafts", {}).get("copywriting")
    ):
        run_dir = ensure_session_dir(client_slug, open_id, state)
        graphic_images = generate_graphic_draft(
            payload=state["drafts"]["copywriting"],
            state=state,
            run_dir=run_dir,
        )
        result["action"] = "generate_graphic_draft"
        result["graphic_images"] = graphic_images
        state_changed = True
    else:
        result["action"] = "noop"
        result["response"] = build_state_summary(state)

    result["state_changed"] = state_changed
    if state_changed and not dry_run:
        save_state(client_slug, open_id, state)
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run router for Wuhan tutoring XHS flow.")
    parser.add_argument("--client", default="wuhan-tutoring")
    parser.add_argument("--open-id", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--audience", default=DEFAULT_AUDIENCE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config-path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = route_message(
        client_slug=args.client,
        open_id=args.open_id,
        message=args.message,
        dry_run=args.dry_run,
        config_path=args.config_path,
        audience=args.audience,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
