#!/usr/bin/env python3
"""共享的小红书图片 prompt 生成器。

飞书审核流和客户路由流都依赖这套模板，避免视觉表达各说各话。
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import common

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
            "service_scene": "课堂讲解、小班授课、老师板书讲题",
            "trust_scene": "真实教学现场、学生听课、老师授课细节",
            "cta_text": "了解课程细节和试听安排",
        },
        "study_plan": {
            "service_scene": "老师与家长讲解专属提升方案、查漏补缺路径",
            "trust_scene": "老师团队围绕学习方案沟通、学情分析场景",
            "cta_text": "点击咨询专属提升方案",
        },
        "brand_trust": {
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


def _image_template_config_path(client_slug: str) -> Path:
    return common.get_client_root(client_slug) / "config" / "image_prompt_templates.yaml"


def load_image_prompt_templates(client_slug: str) -> dict[str, Any]:
    loaded = common.load_yaml_file(_image_template_config_path(client_slug))
    if not loaded:
        return deepcopy(_DEFAULT_IMAGE_TEMPLATE_CONFIG)
    return common.deep_merge(_DEFAULT_IMAGE_TEMPLATE_CONFIG, loaded)


def ensure_template_state(state: dict[str, Any], templates: dict[str, Any]) -> dict[str, str]:
    current = state.setdefault("image_templates", {})
    cover_keys = list((templates.get("cover_templates") or {}).keys())
    graphics_keys = list((templates.get("graphics_templates") or {}).keys())
    if not current.get("cover_template_key"):
        current["cover_template_key"] = cover_keys[0] if cover_keys else "map_coverage"
    if not current.get("graphics_template_key"):
        current["graphics_template_key"] = graphics_keys[0] if graphics_keys else "classroom_focus"
    return current


def cycle_template_key(current_key: str, keys: list[str]) -> str:
    if not keys:
        return current_key
    if current_key not in keys:
        return keys[0]
    index = keys.index(current_key)
    return keys[(index + 1) % len(keys)]


def size_text(templates: dict[str, Any]) -> str:
    defaults = templates.get("defaults") or {}
    width = defaults.get("width", 1080)
    height = defaults.get("height", 1440)
    return f"{width}x{height}"


def extract_sentences(text: str, limit: int) -> list[str]:
    normalized = text.replace("\n", "。")
    parts = [part.strip(" 。；;") for part in normalized.split("。") if part.strip(" 。；;")]
    return parts[:limit]


def format_prompt_list(values: list[str]) -> str:
    return "；".join(value for value in values if value)


def build_cover_prompt(
    payload: dict[str, Any],
    state: dict[str, Any],
    client_slug: str,
) -> str:
    templates = load_image_prompt_templates(client_slug)
    template_state = ensure_template_state(state, templates)
    cover_templates = templates.get("cover_templates") or {}
    template = cover_templates.get(template_state["cover_template_key"]) or next(iter(cover_templates.values()), {})
    style_anchor = (templates.get("defaults") or {}).get("style_anchor", "武汉本地教培招生图文风")
    variants = payload.get("variants") or []
    sub_title = template.get("sub_title_hint") or (variants[0].get("angle") if variants else "")
    return str(template.get("prompt", "")).format(
        style_anchor=style_anchor,
        size_text=size_text(templates),
        main_title=payload.get("cover_title") or payload.get("title") or "",
        sub_title=sub_title,
        local_hint=template.get("local_hint", "武汉本地校区、家长咨询、教培服务场景"),
        cta_text=template.get("cta_text", "点击咨询领取专属方案"),
    )


def build_graphic_prompts(
    payload: dict[str, Any],
    state: dict[str, Any],
    client_slug: str,
) -> list[tuple[str, str]]:
    templates = load_image_prompt_templates(client_slug)
    template_state = ensure_template_state(state, templates)
    graphics_template = (templates.get("graphics_templates") or {}).get(template_state["graphics_template_key"], {})
    content_templates = templates.get("content_templates") or {}
    style_anchor = (templates.get("defaults") or {}).get("style_anchor", "武汉本地教培招生图文风")
    variants = payload.get("variants") or []

    service_variant = variants[0] if variants else {}
    trust_variant = variants[1] if len(variants) > 1 else service_variant

    service_prompt = str((content_templates.get("service") or {}).get("prompt", "")).format(
        style_anchor=style_anchor,
        size_text=size_text(templates),
        main_title=service_variant.get("title") or payload.get("cover_title") or "",
        selling_points=format_prompt_list(extract_sentences(str(service_variant.get("body") or ""), 3)),
        scene_hint=graphics_template.get("service_scene", "课堂讲解、小班授课、老师板书讲题"),
        cta_text=graphics_template.get("cta_text", "了解课程细节和试听安排"),
    )
    trust_prompt = str((content_templates.get("trust") or {}).get("prompt", "")).format(
        style_anchor=style_anchor,
        size_text=size_text(templates),
        main_title=trust_variant.get("title") or payload.get("cover_title") or "",
        sub_title=trust_variant.get("angle") or payload.get("cover_title") or "",
        trust_points=format_prompt_list(extract_sentences(str(trust_variant.get("body") or ""), 3)),
        trust_scene=graphics_template.get("trust_scene", "校区环境、老师团队、家长沟通或教学现场"),
        cta_text=graphics_template.get("cta_text", "点击咨询专属提升方案"),
    )
    return [
        ("graphic_1.png", service_prompt),
        ("graphic_2.png", trust_prompt),
    ]
