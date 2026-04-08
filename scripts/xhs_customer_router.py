#!/usr/bin/env python3
"""Intent routing helpers for the XHS customer flow."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import common
from xhs_feedback_parser import parse_feedback
from xhs_customer_state import ensure_session_dir, load_state, save_state
from xhs_feishu_flow import generate_slide_images, generate_xhs_payload
from gemini_image import generate_image
from xhs_topic_generator import (
    get_all_subjects,
    get_random_topics,
    get_topic_by_title,
    get_topics_by_subject,
)

_TOPIC_HINTS = ("中考", "学科", "押题", "知识点")
_FEEDBACK_HINTS = ("修改", "换一个", "换个", "回到文案", "重新来", "汇总")
TOPIC_STATE = "state_0_topic"
COPYWRITING_STATE = "state_1_copywriting"
COVER_STATE = "state_2_cover"
GRAPHIC_STATE = "state_3_graphics"
DONE_STATE = "state_4_done"
DEFAULT_AUDIENCE = "武汉家长"
_MINIMAL_PNG = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
    "0000000D49444154789C63F8FFFFFF7F0009FB03FD2A86E38A0000000049454E44AE426082"
)
_DEFAULT_IMAGE_TEMPLATE_CONFIG = {
    "defaults": {
        "aspect_ratio": "3:4",
        "width": 1080,
        "height": 1440,
        "style_anchor": "武汉本地教培招生图文风",
    },
    "cover_templates": {
        "map_coverage": {
            "local_hint": "武汉本地校区分布地图、门店覆盖、就近规划中心",
            "sub_title_hint": "家门口更方便，就近安排更省心",
            "cta_text": "点击咨询领取专属方案",
            "prompt": "{style_anchor}，3:4竖版，{size_text}，真实摄影感底图。顶部放超大标题：{main_title}。中上区域补一句副标题：{sub_title}。主体画面表现 {local_hint}。底部加入高对比行动条：{cta_text}。",
        },
        "campus_access": {
            "local_hint": "武汉校区门头、前台接待、家长到店咨询",
            "sub_title_hint": "校区可达，家长决策更直接",
            "cta_text": "预约测评了解就近校区",
            "prompt": "{style_anchor}，3:4竖版，{size_text}，真实摄影感底图。主标题：{main_title}。副标题：{sub_title}。画面主体是 {local_hint}。底部保留高对比CTA：{cta_text}。",
        },
        "parent_consult": {
            "local_hint": "武汉家长与老师面对面咨询、升学规划沟通场景",
            "sub_title_hint": "家长最关心的方案和结果",
            "cta_text": "点击获取升学规划建议",
            "prompt": "{style_anchor}，3:4竖版，{size_text}，真实摄影感底图。顶部主标题：{main_title}。补充一句副标题：{sub_title}。主体画面是 {local_hint}。底部有清晰CTA条：{cta_text}。",
        },
    },
    "graphics_templates": {
        "classroom_focus": {
            "layout_mode": "真实课堂/校区照片打底 + 叠字信息块",
            "headline_style": "白字或黄字大标题 + 黑描边，配短标签块",
            "accent_palette": "红橙黄标题 + 白字信息块，黑底半透明遮罩辅助可读",
            "prompt": "实拍底图 + 叠字信息块，用真实课堂和教学现场做底，保留3到5块可快速扫读的信息。",
            "service_scene": "课堂讲解、小班授课、老师板书讲题",
            "trust_scene": "真实教学现场、学生听课、老师授课细节",
            "cta_text": "了解课程细节和试听安排",
        },
        "study_plan": {
            "layout_mode": "痛点 vs 解决动作分栏，3到5块内容，强对比",
            "headline_style": "痛点词和解决动作用短句大字分层强调",
            "accent_palette": "蓝白底 + 红色强调痛点，黑字辅助说明",
            "prompt": "痛点-解决动作结构，上半区先写家长/学生痛点，下半区给解决动作，全图只保留3到5块。",
            "service_scene": "老师与家长讲解专属提升方案、查漏补缺路径",
            "trust_scene": "老师团队围绕学习方案沟通、学情分析场景",
            "cta_text": "点击咨询专属提升方案",
        },
        "brand_trust": {
            "layout_mode": "蓝白分块信息卡，3到5块内容，快读优先",
            "headline_style": "蓝底白字或白底蓝字的大字标题，短句直给",
            "accent_palette": "蓝白主色，黑字辅助，少量红色仅用于重点提醒",
            "prompt": "蓝白信息卡，3到5块信息块，家长一眼扫懂，像本地教培常见的课程说明图。",
            "service_scene": "老师一对一答疑、教学服务说明",
            "trust_scene": "校区环境、老师团队、家长沟通、品牌展示",
            "cta_text": "预约测评了解师资与服务",
        },
    },
    "content_templates": {
        "service": {
            "prompt": "{style_anchor}，3:4竖版，{size_text}，真实课堂或咨询场景打底。主标题：{main_title}。画面主体是 {scene_hint}。下方用2到4条短卖点展示：{selling_points}。底部保留轻行动条：{cta_text}。",
        },
        "trust": {
            "prompt": "{style_anchor}，3:4竖版，{size_text}，真实校区环境、老师团队、家长沟通或教学现场照片打底。主标题：{main_title}。副标题：{sub_title}。下方用2到3条背书信息展示：{trust_points}。主体画面突出 {trust_scene}。底部保留轻CTA：{cta_text}。",
        },
    },
}
_CONFIRMATION_HINTS = (
    "可以",
    "继续",
    "确认",
    "通过",
    "就这个",
    "就这样",
    "没问题",
)


def _jsonish(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    return json.dumps(value, ensure_ascii=False)


def _image_template_config_path(client_slug: str) -> Path:
    return common.get_client_root(client_slug) / "config" / "image_prompt_templates.yaml"


def load_image_prompt_templates(client_slug: str) -> dict[str, Any]:
    loaded = common.load_yaml_file(_image_template_config_path(client_slug))
    if not loaded:
        return deepcopy(_DEFAULT_IMAGE_TEMPLATE_CONFIG)
    return common.deep_merge(_DEFAULT_IMAGE_TEMPLATE_CONFIG, loaded)


def _ensure_template_state(state: dict[str, Any], templates: dict[str, Any]) -> dict[str, str]:
    current = state.setdefault("image_templates", {})
    cover_keys = list((templates.get("cover_templates") or {}).keys())
    graphics_keys = list((templates.get("graphics_templates") or {}).keys())
    if not current.get("cover_template_key"):
        current["cover_template_key"] = cover_keys[0] if cover_keys else "map_coverage"
    if not current.get("graphics_template_key"):
        current["graphics_template_key"] = graphics_keys[0] if graphics_keys else "classroom_focus"
    return current


def _cycle_template_key(current_key: str, keys: list[str]) -> str:
    if not keys:
        return current_key
    if current_key not in keys:
        return keys[0]
    index = keys.index(current_key)
    return keys[(index + 1) % len(keys)]


def _size_text(templates: dict[str, Any]) -> str:
    defaults = templates.get("defaults") or {}
    width = defaults.get("width", 1080)
    height = defaults.get("height", 1440)
    return f"{width}x{height}"


def _extract_sentences(text: str, limit: int) -> list[str]:
    normalized = text.replace("\n", "。")
    parts = [part.strip(" 。；;") for part in normalized.split("。") if part.strip(" 。；;")]
    return parts[:limit]


def _format_prompt_list(values: list[str]) -> str:
    return "；".join(value for value in values if value)


def _build_cover_prompt(
    payload: dict[str, Any],
    state: dict[str, Any],
    client_slug: str,
) -> str:
    templates = load_image_prompt_templates(client_slug)
    template_state = _ensure_template_state(state, templates)
    cover_templates = templates.get("cover_templates") or {}
    template = cover_templates.get(template_state["cover_template_key"]) or next(iter(cover_templates.values()), {})
    style_anchor = (templates.get("defaults") or {}).get("style_anchor", "武汉本地教培招生图文风")
    variants = payload.get("variants") or []
    sub_title = template.get("sub_title_hint") or (variants[0].get("angle") if variants else "")
    return str(template.get("prompt", "")).format(
        style_anchor=style_anchor,
        size_text=_size_text(templates),
        main_title=payload.get("cover_title") or payload.get("title") or "",
        sub_title=sub_title,
        local_hint=template.get("local_hint", "武汉本地校区、家长咨询、教培服务场景"),
        cta_text=template.get("cta_text", "点击咨询领取专属方案"),
        layout_mode=template.get("layout_mode", "高密度教培投放封面"),
        headline_style=template.get("headline_style", "短句粗黑大字、描边排版"),
        accent_palette=template.get("accent_palette", "红橙黄主色 + 黑白支撑"),
    )


def _build_graphic_prompts(
    payload: dict[str, Any],
    state: dict[str, Any],
    client_slug: str,
) -> list[tuple[str, str]]:
    templates = load_image_prompt_templates(client_slug)
    template_state = _ensure_template_state(state, templates)
    graphics_template = (templates.get("graphics_templates") or {}).get(template_state["graphics_template_key"], {})
    content_templates = templates.get("content_templates") or {}
    style_anchor = (templates.get("defaults") or {}).get("style_anchor", "武汉本地教培招生图文风")
    variants = payload.get("variants") or []

    service_variant = variants[0] if variants else {}
    trust_variant = variants[1] if len(variants) > 1 else service_variant

    service_prompt = str((content_templates.get("service") or {}).get("prompt", "")).format(
        style_anchor=style_anchor,
        size_text=_size_text(templates),
        main_title=service_variant.get("title") or payload.get("cover_title") or "",
        selling_points=_format_prompt_list(_extract_sentences(str(service_variant.get("body") or ""), 3)),
        family_prompt=graphics_template.get("prompt", "蓝白信息卡，3到5块信息块，家长一眼扫懂"),
        layout_mode=graphics_template.get("layout_mode", "蓝白分块信息卡，3到5块内容"),
        headline_style=graphics_template.get("headline_style", "短句大字"),
        accent_palette=graphics_template.get("accent_palette", "蓝白主色"),
        scene_hint=graphics_template.get("service_scene", "课堂讲解、小班授课、老师板书讲题"),
        cta_text=graphics_template.get("cta_text", "了解课程细节和试听安排"),
    )
    trust_prompt = str((content_templates.get("trust") or {}).get("prompt", "")).format(
        style_anchor=style_anchor,
        size_text=_size_text(templates),
        main_title=trust_variant.get("title") or payload.get("cover_title") or "",
        sub_title=trust_variant.get("angle") or payload.get("cover_title") or "",
        trust_points=_format_prompt_list(_extract_sentences(str(trust_variant.get("body") or ""), 3)),
        family_prompt=graphics_template.get("prompt", "蓝白信息卡，3到5块信息块，家长一眼扫懂"),
        layout_mode=graphics_template.get("layout_mode", "蓝白分块信息卡，3到5块内容"),
        headline_style=graphics_template.get("headline_style", "短句大字"),
        accent_palette=graphics_template.get("accent_palette", "蓝白主色"),
        trust_scene=graphics_template.get("trust_scene", "校区环境、老师团队、家长沟通或教学现场"),
        cta_text=graphics_template.get("cta_text", "点击咨询专属提升方案"),
    )
    return [
        ("graphic_1.png", service_prompt),
        ("graphic_2.png", trust_prompt),
    ]


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
    current_state = state.get("current_state", "")

    if any(hint in text for hint in _FEEDBACK_HINTS):
        return {
            "intent": "feedback_request",
            "feedback": parse_feedback(text, current_state),
        }

    if (
        current_state == COVER_STATE
        and "封面图" in text
        and any(hint in text for hint in _CONFIRMATION_HINTS)
    ):
        return {"intent": "selection_or_confirmation"}

    if (
        current_state == GRAPHIC_STATE
        and "配图" in text
        and any(hint in text for hint in _CONFIRMATION_HINTS)
    ):
        return {"intent": "selection_or_confirmation"}

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


def _extract_subject(message: str) -> str | None:
    for subject in get_all_subjects():
        if subject in message:
            return subject
    return None


def _format_topic_option(topic: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": topic["title"],
        "angle": topic.get("subtitle") or topic.get("audience") or "",
        "tags": list(topic.get("tags", []))[:8],
        "reference_style": topic.get("style"),
        "audience": topic.get("audience"),
    }


def generate_topic_drafts(message: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    subject = _extract_subject(message)
    candidates: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    matched_topic = get_topic_by_title(message)
    if matched_topic:
        candidates.append(matched_topic)
        seen_titles.add(matched_topic["title"])

    if subject:
        for topic in get_topics_by_subject(subject):
            if topic["title"] in seen_titles:
                continue
            candidates.append(topic)
            seen_titles.add(topic["title"])

    for topic in get_random_topics(5):
        if topic["title"] in seen_titles:
            continue
        candidates.append(topic)
        seen_titles.add(topic["title"])
        if len(candidates) >= 5:
            break

    options = [_format_topic_option(topic) for topic in candidates[:5]]
    drafts = state.setdefault("drafts", {})
    drafts["topics"] = options
    state["current_state"] = TOPIC_STATE
    state["last_user_intent"] = "topic_request"
    return options


_ORDINAL_MAP = {
    "1": 1,
    "一": 1,
    "2": 2,
    "二": 2,
    "3": 3,
    "三": 3,
    "4": 4,
    "四": 4,
    "5": 5,
    "五": 5,
}


def _select_topic_option(message: str, topics: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not topics:
        return None

    for pattern in (
        r"第\s*([12345一二三四五])\s*个",
        r"第\s*([12345一二三四五])",
        r"选\s*([12345一二三四五])",
    ):
        match = __import__("re").search(pattern, message)
        if not match:
            continue
        index = _ORDINAL_MAP.get(match.group(1))
        if index is None:
            continue
        if 1 <= index <= len(topics):
            return topics[index - 1]

    for topic in topics:
        title = str(topic.get("title") or "")
        if title and title in message:
            return topic
    return None


def generate_copywriting_draft(
    topic: str,
    audience: str,
    config: dict[str, Any],
    state: dict[str, Any],
    dry_run: bool = False,
    client_slug: str = "wuhan-tutoring",
) -> dict[str, Any]:
    client_root = common.get_client_root(client_slug)
    system_prompt_path = client_root / "prompts" / "system-prompt.md"
    style_guide_path = client_root / "references" / "文案风格指南.md"
    system_prompt_text = (
        system_prompt_path.read_text(encoding="utf-8")
        if system_prompt_path.exists()
        else None
    )
    style_guide_text = (
        style_guide_path.read_text(encoding="utf-8")
        if style_guide_path.exists()
        else None
    )
    payload = generate_xhs_payload(
        topic,
        audience,
        config,
        dry_run=dry_run,
        system_prompt_text=system_prompt_text,
        style_guide_text=style_guide_text,
    )
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
    client_slug: str = "wuhan-tutoring",
    rotate_template: bool = False,
) -> list[str]:
    templates = load_image_prompt_templates(client_slug)
    template_state = _ensure_template_state(state, templates)
    if rotate_template:
        cover_keys = list((templates.get("cover_templates") or {}).keys())
        template_state["cover_template_key"] = _cycle_template_key(
            template_state["cover_template_key"],
            cover_keys,
        )
    payload = deepcopy(payload)
    payload["cover_prompt"] = _build_cover_prompt(payload, state, client_slug)
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
    count: int = 2,
    dry_run: bool = False,
    config: dict[str, Any] | None = None,
    client_slug: str = "wuhan-tutoring",
    rotate_template: bool = False,
) -> list[str]:
    graphic_dir = common.ensure_dir(run_dir / "graphics")
    generated: list[str] = []
    config = config or {}
    templates = load_image_prompt_templates(client_slug)
    template_state = _ensure_template_state(state, templates)
    if rotate_template:
        graphic_keys = list((templates.get("graphics_templates") or {}).keys())
        template_state["graphics_template_key"] = _cycle_template_key(
            template_state["graphics_template_key"],
            graphic_keys,
        )
    prompt_specs = _build_graphic_prompts(payload, state, client_slug)[:count]
    for filename, prompt in prompt_specs:
        target = graphic_dir / filename
        if dry_run:
            _write_placeholder_png(target)
        else:
            generate_image(prompt, target, config=config, allow_placeholder=True)
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


def confirm_cover(state: dict[str, Any]) -> dict[str, Any]:
    drafts = state.setdefault("drafts", {})
    confirmed = state.setdefault("confirmed", {})
    confirmed["cover"] = list(drafts.get("cover_images") or [])
    drafts["graphic_images"] = []
    state["current_state"] = GRAPHIC_STATE
    return state


def confirm_graphics(state: dict[str, Any]) -> dict[str, Any]:
    drafts = state.setdefault("drafts", {})
    confirmed = state.setdefault("confirmed", {})
    confirmed["graphics"] = list(drafts.get("graphic_images") or [])
    state["current_state"] = DONE_STATE
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
        classified["intent"] == "topic_request"
    ):
        topic_options = generate_topic_drafts(message, state)
        result["action"] = "generate_topic_drafts"
        result["topic_options"] = topic_options
        state_changed = True
    elif (
        classified["intent"] == "selection_or_confirmation"
        and state.get("current_state") == TOPIC_STATE
        and state.get("drafts", {}).get("topics")
    ):
        selected_topic = _select_topic_option(
            message,
            list(state.get("drafts", {}).get("topics") or []),
        )
        if selected_topic:
            state.setdefault("confirmed", {})["topic"] = selected_topic["title"]
            state["current_topic_id"] = common.slugify(selected_topic["title"])
            state["current_state"] = COPYWRITING_STATE
            config = {} if dry_run else common.load_config(config_path)
            payload = generate_copywriting_draft(
                topic=str(selected_topic["title"]),
                audience=str(selected_topic.get("audience") or audience),
                config=config,
                state=state,
                dry_run=dry_run,
                client_slug=client_slug,
            )
            result["action"] = "confirm_topic_and_generate_copywriting_draft"
            result["payload"] = payload
            state_changed = True
        else:
            result["action"] = "noop"
            result["response"] = build_state_summary(state)
    elif (
        classified["intent"] == "selection_or_confirmation"
        and state.get("current_state") == COPYWRITING_STATE
        and state.get("drafts", {}).get("copywriting")
    ):
        confirm_copywriting(state)
        result["action"] = "confirm_copywriting"
        result["confirmed_copywriting"] = state.get("confirmed", {}).get("copywriting")
        state_changed = True
    elif (
        classified["intent"] == "selection_or_confirmation"
        and state.get("current_state") == COVER_STATE
        and state.get("drafts", {}).get("cover_images")
    ):
        confirm_cover(state)
        result["action"] = "confirm_cover"
        result["confirmed_cover"] = state.get("confirmed", {}).get("cover")
        state_changed = True
    elif (
        classified["intent"] == "selection_or_confirmation"
        and state.get("current_state") == GRAPHIC_STATE
        and state.get("drafts", {}).get("graphic_images")
    ):
        confirm_graphics(state)
        result["action"] = "confirm_graphics"
        result["confirmed_graphics"] = state.get("confirmed", {}).get("graphics")
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
            client_slug=client_slug,
        )
        result["action"] = "generate_cover_draft"
        result["cover_images"] = cover_images
        state_changed = True
    elif (
        classified["intent"] == "graphic_request"
        and state.get("drafts", {}).get("copywriting")
    ):
        config = {} if dry_run else common.load_config(config_path)
        run_dir = ensure_session_dir(client_slug, open_id, state)
        graphic_images = generate_graphic_draft(
            payload=state["drafts"]["copywriting"],
            state=state,
            run_dir=run_dir,
            dry_run=dry_run,
            config=config,
            client_slug=client_slug,
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
