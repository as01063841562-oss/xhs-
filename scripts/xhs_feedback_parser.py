#!/usr/bin/env python3
"""Parse XHS customer feedback into structured update intents."""

from __future__ import annotations

import re
from typing import Any

STATE_1_COPYWRITING = "state_1_copywriting"
STATE_2_COVER = "state_2_cover"
STATE_3_GRAPHICS = "state_3_graphics"

_PUNCT_PREFIX = re.compile(r"^[\s,，。．.：:、\-–—~·]+")


def _clean_instruction(text: str) -> str:
    return _PUNCT_PREFIX.sub("", text.strip())


def _suffix_after(message: str, trigger: str) -> str:
    index = message.find(trigger)
    if index < 0:
        return ""
    return _clean_instruction(message[index + len(trigger) :])


def parse_feedback(message: str, current_state: str) -> dict[str, Any]:
    """Convert a feedback message into a structured routing payload."""

    text = (message or "").strip()

    if "回到文案" in text:
        return {
            "operation": "rollback",
            "target_state": STATE_1_COPYWRITING,
        }

    if "重新来封面图" in text or "重新来封面" in text:
        return {
            "operation": "regenerate_current",
            "target_state": STATE_2_COVER,
        }

    if "重新来配图" in text or "重新来图" in text:
        return {
            "operation": "regenerate_current",
            "target_state": STATE_3_GRAPHICS,
        }

    if "重新来当前阶段" in text:
        return {
            "operation": "regenerate_current",
            "target_state": current_state,
        }

    if "标题换一个" in text:
        return {
            "operation": "partial_update",
            "target_state": current_state,
            "scope": {"type": "title"},
            "instruction": _suffix_after(text, "标题换一个"),
        }

    if "修改标题" in text:
        return {
            "operation": "partial_update",
            "target_state": current_state,
            "scope": {"type": "title"},
            "instruction": _suffix_after(text, "修改标题"),
        }

    paragraph_match = re.search(r"文案第(\d+)段", text)
    if paragraph_match:
        index = int(paragraph_match.group(1))
        return {
            "operation": "partial_update",
            "target_state": current_state,
            "scope": {"type": "paragraph", "index": index},
            "instruction": _clean_instruction(
                text[paragraph_match.end() :]
            ),
        }

    if "封面图" in text and "背景" in text:
        instruction = _clean_instruction(text.split("背景", 1)[1] if "背景" in text else "")
        return {
            "operation": "partial_update",
            "target_state": STATE_2_COVER,
            "scope": {"type": "cover_background"},
            "instruction": instruction,
        }

    if "封面图" in text and ("换成" in text or "换个" in text or "风格" in text):
        instruction = _clean_instruction(text.split("封面图", 1)[1] if "封面图" in text else "")
        if "换成" in instruction:
            instruction = _clean_instruction(instruction.split("换成", 1)[1])
        elif "换个" in instruction:
            instruction = _clean_instruction(instruction.split("换个", 1)[1])
        return {
            "operation": "partial_update",
            "target_state": STATE_2_COVER,
            "scope": {"type": "cover_background"},
            "instruction": instruction,
        }

    if "生成封面图" in text:
        return {
            "operation": "partial_update",
            "target_state": STATE_2_COVER,
            "scope": {"type": "cover_background"},
            "instruction": _suffix_after(text, "生成封面图"),
        }

    if "配图" in text or "生成配图" in text:
        trigger = "生成配图" if "生成配图" in text else "配图"
        instruction = _suffix_after(text, trigger)
        if "换成" in instruction:
            instruction = _clean_instruction(instruction.split("换成", 1)[1])
        elif "换个" in instruction:
            instruction = _clean_instruction(instruction.split("换个", 1)[1])
        return {
            "operation": "partial_update",
            "target_state": STATE_3_GRAPHICS,
            "scope": {"type": "graphic_style"},
            "instruction": instruction,
        }

    if "汇总" in text:
        return {"operation": "summary"}

    if "重新来" in text:
        return {
            "operation": "regenerate_current",
            "target_state": current_state,
        }

    return {"operation": "unknown"}
