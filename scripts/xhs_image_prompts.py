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
        "image_count": {
            "cover": 1,
            "graphics": 2,
        },
        "style_anchor": "武汉本地高密度教培投放图，大字，强 CTA，真实本地场景",
        "negative_prompt": (
            "不要极简风，不要高级品牌广告，不要奶油/紫色调，不要抽象信息图，"
            "不要低密度排版，不要长段正文，不要蓝紫科技风，不要弱 CTA。"
        ),
    },
    "cover_templates": {
        "promo_blast": {
            "label": "爆炸大字转化封",
            "layout_mode": "巨型主标题 + 多条短信息 + 底部强 CTA",
            "headline_style": "短句粗黑大字、描边、贴纸感、密集排版",
            "accent_palette": "红橙黄主色 + 黑白支撑，蓝色只做小点缀",
            "local_hint": "真实武汉校区门头、课堂、咨询区或走廊照片",
            "sub_title_hint": "到店试听、提分测评、本地规划直接接住咨询转化",
            "cta_text": "点击咨询抢试听名额",
            "prompt": (
                "{style_anchor}，3:4竖版，{size_text}，真实摄影感底图。做成武汉本地高密度教培投放图，"
                "版式为 {layout_mode}。标题区必须是 {headline_style}，颜色锚定 {accent_palette}。"
                "主体底图使用 {local_hint} 的真实场景，不要高级品牌海报。"
                "主标题：{main_title}。副标题：{sub_title}。"
                "画面塞满可快速扫读的信息，像家长刷到就会停下的本地投放封面。"
                "底部放强 CTA 行动条：{cta_text}。"
            ),
        },
        "promo_collage": {
            "label": "拼图照片转化封",
            "layout_mode": "2到4张真实校园/课堂/走廊照片拼贴 + 巨型标题 + 强 CTA",
            "headline_style": "短句大字、重描边、贴边排版、密集信息块",
            "accent_palette": "红橙黄主色 + 黑白支撑，蓝色只做标签小角标",
            "local_hint": "真实武汉校园门头、课堂板书、咨询区、走廊到校动线",
            "sub_title_hint": "多场景同屏展示，到校感和可信度一起拉满",
            "cta_text": "私信领取到校规划",
            "prompt": (
                "{style_anchor}，3:4竖版，{size_text}，真实摄影感底图。做成拼贴式高密度教培投放图，"
                "版式为 {layout_mode}。标题区使用 {headline_style}，主色按 {accent_palette} 执行。"
                "画面主体必须是 {local_hint} 的真实校园照片拼贴，不是抽象拼贴。"
                "主标题：{main_title}。副标题：{sub_title}。"
                "信息密度要高，既要真实校园感，也要明显转化广告感。"
                "底部放强 CTA 行动条：{cta_text}。"
            ),
        },
        "promo_map": {
            "label": "地图覆盖转化封",
            "layout_mode": "武汉地图 / 校区覆盖 + 巨型标题 + 到店 CTA",
            "headline_style": "短句粗黑大字、地图贴纸标注、密集信息条",
            "accent_palette": "红橙黄主色 + 黑白支撑，蓝色只做路线或定位小点缀",
            "local_hint": "武汉本地校区分布地图、门店覆盖、就近到校路线",
            "sub_title_hint": "家门口就近安排，先看最近校区再约试听",
            "cta_text": "点击咨询就近校区",
            "prompt": (
                "{style_anchor}，3:4竖版，{size_text}，真实摄影感底图。做成带地图 framing 的高密度教培投放图，"
                "版式为 {layout_mode}。标题区使用 {headline_style}，颜色锚定 {accent_palette}。"
                "主体视觉必须围绕 {local_hint}，清楚展示武汉地图、本地校区标注或覆盖范围。"
                "主标题：{main_title}。副标题：{sub_title}。"
                "画面既像本地投放广告，也要让家长一眼知道离我近。"
                "底部放强 CTA 行动条：{cta_text}。"
            ),
        },
    },
    "graphics_templates": {
        "info_card_blue": {
            "label": "蓝白信息卡",
            "layout_mode": "蓝白分块信息卡，3到5块内容，快读优先",
            "headline_style": "蓝底白字或白底蓝字的大字标题，短句直给",
            "accent_palette": "蓝白主色，黑字辅助，少量红色仅用于重点提醒",
            "service_scene": "蓝白信息卡模块、步骤卡、提分路径块",
            "trust_scene": "蓝白背书卡、成果/师资/安排分块信息",
            "cta_text": "私信领取课程安排",
            "prompt": (
                "蓝白信息卡，3到5块信息块，家长一眼扫懂，"
                "像本地教培常见的课程说明图，不要长段正文，不要抽象图表。"
            ),
        },
        "pain_solution": {
            "label": "痛点解决图",
            "layout_mode": "痛点 vs 解决动作分栏，3到5块内容，强对比",
            "headline_style": "痛点词和解决动作用短句大字分层强调",
            "accent_palette": "蓝白底 + 红色强调痛点，黑字辅助说明",
            "service_scene": "家长痛点、学习卡点、对应解决动作分栏展示",
            "trust_scene": "问题-动作-结果三段式说明，配少量背书块",
            "cta_text": "点击咨询解决方案",
            "prompt": (
                "痛点-解决动作结构，上半区先写家长/学生痛点，下半区给解决动作，"
                "全图只保留3到5块，读感像教培投放里的问题解法图。"
            ),
        },
        "onsite_overlay": {
            "label": "实拍叠字图",
            "layout_mode": "真实校区/课堂/走廊照片打底 + 叠字信息块",
            "headline_style": "白字或黄字大标题 + 黑描边，配短标签块",
            "accent_palette": "红橙黄标题 + 白字信息块，黑底半透明遮罩辅助可读",
            "service_scene": "真实课堂、校区、走廊、咨询区实拍底图",
            "trust_scene": "真实老师、家长沟通、学生到校、校区环境实拍底图",
            "cta_text": "私信看现场安排",
            "prompt": (
                "实拍底图 + 叠字信息块，用真实校区/课堂/走廊/咨询照片做底，"
                "只放3到5块可快速扫读的信息，不要长段解释。"
            ),
        },
    },
    "content_templates": {
        "service": {
            "prompt": (
                "{style_anchor}，3:4竖版，{size_text}，真实课堂或咨询场景打底。按 {layout_mode} 生成内容图。"
                "风格说明：{family_prompt}。标题区使用 {headline_style}，颜色按 {accent_palette} 执行。"
                "主标题：{main_title}。画面主体参考 {scene_hint}。"
                "主体信息只保留 3到5块，快读优先：{selling_points}。"
                "底部保留 CTA：{cta_text}。面向家长快速阅读，不要长段正文，不要高级品牌感。"
            ),
        },
        "trust": {
            "prompt": (
                "{style_anchor}，3:4竖版，{size_text}，真实校区环境、老师团队、家长沟通或教学现场照片打底。按 {layout_mode} 生成内容图。"
                "风格说明：{family_prompt}。标题区使用 {headline_style}，颜色按 {accent_palette} 执行。"
                "主标题：{main_title}。辅助标题：{sub_title}。画面主体参考 {trust_scene}。"
                "背书/动作信息只保留 3到5块：{trust_points}。"
                "底部保留 CTA：{cta_text}。让家长一眼扫懂，不要长段解释，不要抽象信息图。"
            ),
        },
    },
}

_LEGACY_COVER_TEMPLATE_KEYS = {
    "map_coverage": "promo_map",
    "campus_access": "promo_collage",
    "parent_consult": "promo_blast",
}

_LEGACY_COVER_TEMPLATE_OVERRIDES = {
    "map_coverage": {
        "local_hint": "武汉本地校区分布地图、门店覆盖、就近规划中心",
        "sub_title_hint": "家门口更方便，就近安排更省心",
        "cta_text": "点击咨询领取专属方案",
    },
    "campus_access": {
        "local_hint": "武汉校区门头、前台接待、家长到店咨询",
        "sub_title_hint": "校区可达，家长决策更直接",
        "cta_text": "预约测评了解就近校区",
    },
    "parent_consult": {
        "local_hint": "武汉家长与老师面对面咨询、升学规划沟通场景",
        "sub_title_hint": "家长最关心的方案和结果",
        "cta_text": "点击获取升学规划建议",
    },
}

_LEGACY_GRAPHICS_TEMPLATE_KEYS = {
    "classroom_focus": "onsite_overlay",
    "study_plan": "pain_solution",
    "brand_trust": "info_card_blue",
}

_LEGACY_GRAPHICS_TEMPLATE_OVERRIDES = {
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
}


def _image_template_config_path(client_slug: str) -> Path:
    return common.get_client_root(client_slug) / "config" / "image_prompt_templates.yaml"


def load_image_prompt_templates(client_slug: str) -> dict[str, Any]:
    loaded = common.load_yaml_file(_image_template_config_path(client_slug))
    if not loaded:
        return deepcopy(_DEFAULT_IMAGE_TEMPLATE_CONFIG)
    return common.deep_merge(_DEFAULT_IMAGE_TEMPLATE_CONFIG, loaded)


def _normalize_template_key(
    current_key: Any,
    available_keys: list[str],
    legacy_aliases: dict[str, str],
    fallback: str,
) -> str:
    normalized = legacy_aliases.get(str(current_key or ""), str(current_key or ""))
    if normalized and normalized in available_keys:
        return normalized
    if available_keys:
        return available_keys[0]
    return fallback


def ensure_template_state(state: dict[str, Any], templates: dict[str, Any]) -> dict[str, str]:
    current = state.setdefault("image_templates", {})
    cover_keys = list((templates.get("cover_templates") or {}).keys())
    graphics_keys = list((templates.get("graphics_templates") or {}).keys())
    current["cover_template_key"] = _normalize_template_key(
        current.get("cover_template_key"),
        cover_keys,
        _LEGACY_COVER_TEMPLATE_KEYS,
        "promo_blast",
    )
    current["graphics_template_key"] = _normalize_template_key(
        current.get("graphics_template_key"),
        graphics_keys,
        _LEGACY_GRAPHICS_TEMPLATE_KEYS,
        "info_card_blue",
    )
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


def _template_with_legacy_overrides(
    template_map: dict[str, Any],
    normalized_key: str,
    raw_key: Any,
    legacy_overrides: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    template = deepcopy(template_map.get(normalized_key) or next(iter(template_map.values()), {}))
    override = legacy_overrides.get(str(raw_key or ""))
    if override:
        template.update(override)
    return template


def build_cover_prompt(
    payload: dict[str, Any],
    state: dict[str, Any],
    client_slug: str,
) -> str:
    templates = load_image_prompt_templates(client_slug)
    raw_cover_key = (state.get("image_templates") or {}).get("cover_template_key")
    template_state = ensure_template_state(state, templates)
    cover_templates = templates.get("cover_templates") or {}
    template = _template_with_legacy_overrides(
        cover_templates,
        template_state["cover_template_key"],
        raw_cover_key,
        _LEGACY_COVER_TEMPLATE_OVERRIDES,
    )
    style_anchor = (templates.get("defaults") or {}).get(
        "style_anchor",
        "武汉本地高密度教培投放图，大字，强 CTA，真实本地场景",
    )
    variants = payload.get("variants") or []
    sub_title = template.get("sub_title_hint") or (variants[0].get("angle") if variants else "")
    return str(template.get("prompt", "")).format(
        style_anchor=style_anchor,
        size_text=size_text(templates),
        main_title=payload.get("cover_title") or payload.get("title") or "",
        sub_title=sub_title,
        local_hint=template.get("local_hint", "武汉本地校区、家长咨询、教培服务场景"),
        cta_text=template.get("cta_text", "点击咨询领取专属方案"),
        layout_mode=template.get("layout_mode", "高密度教培投放封面"),
        headline_style=template.get("headline_style", "短句粗黑大字、描边排版"),
        accent_palette=template.get("accent_palette", "红橙黄主色 + 黑白支撑"),
    )


def build_graphic_prompts(
    payload: dict[str, Any],
    state: dict[str, Any],
    client_slug: str,
) -> list[tuple[str, str]]:
    templates = load_image_prompt_templates(client_slug)
    raw_graphics_key = (state.get("image_templates") or {}).get("graphics_template_key")
    template_state = ensure_template_state(state, templates)
    graphics_template = _template_with_legacy_overrides(
        templates.get("graphics_templates") or {},
        template_state["graphics_template_key"],
        raw_graphics_key,
        _LEGACY_GRAPHICS_TEMPLATE_OVERRIDES,
    )
    content_templates = templates.get("content_templates") or {}
    style_anchor = (templates.get("defaults") or {}).get(
        "style_anchor",
        "武汉本地高密度教培投放图，大字，强 CTA，真实本地场景",
    )
    variants = payload.get("variants") or []

    service_variant = variants[0] if variants else {}
    trust_variant = variants[1] if len(variants) > 1 else service_variant

    service_prompt = str((content_templates.get("service") or {}).get("prompt", "")).format(
        style_anchor=style_anchor,
        size_text=size_text(templates),
        main_title=service_variant.get("title") or payload.get("cover_title") or "",
        selling_points=format_prompt_list(extract_sentences(str(service_variant.get("body") or ""), 3)),
        family_prompt=graphics_template.get("prompt", "蓝白信息卡，3到5块信息块，家长一眼扫懂"),
        layout_mode=graphics_template.get("layout_mode", "蓝白分块信息卡，3到5块内容"),
        headline_style=graphics_template.get("headline_style", "短句大字"),
        accent_palette=graphics_template.get("accent_palette", "蓝白主色"),
        scene_hint=graphics_template.get("service_scene", "课堂讲解、小班授课、老师板书讲题"),
        cta_text=graphics_template.get("cta_text", "了解课程细节和试听安排"),
    )
    trust_prompt = str((content_templates.get("trust") or {}).get("prompt", "")).format(
        style_anchor=style_anchor,
        size_text=size_text(templates),
        main_title=trust_variant.get("title") or payload.get("cover_title") or "",
        sub_title=trust_variant.get("angle") or payload.get("cover_title") or "",
        trust_points=format_prompt_list(extract_sentences(str(trust_variant.get("body") or ""), 3)),
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
