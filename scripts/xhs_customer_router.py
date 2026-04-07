#!/usr/bin/env python3
"""Intent routing helpers for the XHS customer flow."""

from __future__ import annotations

import json
import re
from typing import Any

from xhs_feedback_parser import parse_feedback

_TOPIC_HINTS = ("中考", "学科", "押题", "知识点")
_FEEDBACK_HINTS = ("修改", "换一个", "换个", "回到文案", "重新来", "汇总")


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
