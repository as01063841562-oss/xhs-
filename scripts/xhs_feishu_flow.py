#!/usr/bin/env python3
"""小红书 + 飞书端到端流程脚本。

完整流程：
  1. 生成小红书素材包（文案 + 标签 + 封面 prompt）
  2. 生成封面图（Gemini 网页自动化或占位图）
  3. 上传图片到飞书
  4. 发送审核卡片到飞书（✅通过 / 刷新封面图 / 刷新内容配图）
  5. 等待飞书 card.action.trigger 回流
  6. 通过 → 发送最终稿卡片；修改/重写 → 先打开修改说明卡，填写后再重新生成审核卡

用法：
  python scripts/xhs_feishu_flow.py --topic "主题" --audience "目标人群"
  python scripts/xhs_feishu_flow.py --topic "主题" --dry-run   # 占位图+跳过飞书
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import OUTPUT_DIR, ensure_dir, load_config, make_run_dir, save_json_file, save_text_file, timestamp
from feishu_client import FeishuClient
from gemini_image import generate_image, _generate_placeholder, GeminiImageError
from xhs_image_prompts import build_cover_prompt, build_graphic_prompts, extract_sentences, ensure_template_state, load_image_prompt_templates
from xhs_image_layouts import render_base_image_overlay
from xhs_topic_generator import get_topic_by_title, get_topics_by_subject, WUHAN_TOPICS
from xhs_image_renderer import render_image

DEFAULT_REVIEW_CLIENT_SLUG = "wuhan-tutoring"
DEFAULT_REVIEW_IMAGE_TEMPLATES = {
    "cover_template_key": "parent_consult",
    "graphics_template_key": "study_plan",
}


# ── 小红书素材包生成（复用 xhs_generate 的 stub 逻辑） ──────

def generate_xhs_payload(
    topic: str,
    audience: str,
    config: dict[str, Any],
    dry_run: bool = False,
    revision_mode: str | None = None,
    revision_notes: str | None = None,
    revision_scope: str | None = None,
    existing_payload: dict[str, Any] | None = None,
    system_prompt_text: str | None = None,
    style_guide_text: str | None = None,
) -> dict[str, Any]:
    """生成小红书素材包。

    dry_run 时使用 stub 数据；revision_mode 用于修改/重写回路。
    真实模式下如果文本后端失败，应直接报错，不能静默回退成演示 stub。
    """
    if not dry_run:
        from llm_client import OpenAICompatibleLLM

        client = OpenAICompatibleLLM(config)
        client.require_ready()
        system_sections = [
            "你是一名擅长教育行业内容增长的小红书策划。"
            "请输出严格 JSON，字段必须包含：positioning, cover_title, cover_prompt, hashtags, publish_checklist, variants。"
            "variants 必须有 3 条，每条包含 title, body, angle。"
        ]
        if system_prompt_text:
            system_sections.append(
                "客户专用系统提示词如下，请优先遵守：\n"
                f"{system_prompt_text}"
            )
        if style_guide_text:
            system_sections.append(
                "客户专用文案风格指南如下，请作为固定写作约束：\n"
                f"{style_guide_text}"
            )
        system = "\n\n".join(system_sections)
        revision_hint = ""
        if revision_mode == "modify":
            revision_hint = (
                "当前处于修改版，请在保留主题和核心观点的前提下，"
                "增强开头钩子，压缩冗余表达，并让标题更像可直接发布的小红书笔记。"
            )
        elif revision_mode == "rewrite":
            revision_hint = (
                "当前处于重写版，请完全更换切入角度、标题和表达节奏，"
                "但仍围绕同一主题输出可直接人工复审的素材包。"
            )
        if revision_scope:
            revision_hint += f"修改范围：{revision_scope}。\n"
        if revision_notes:
            revision_hint += (
                "用户的修改说明如下，请严格遵守并尽量保留原意：\n"
                f"{revision_notes}\n"
            )
        existing_hint = ""
        if existing_payload:
            existing_hint = (
                "现有初稿如下，仅供参考，不要逐字照搬：\n"
                f"{json.dumps(existing_payload, ensure_ascii=False, indent=2)}\n"
            )
        user = (
            f"主题：{topic}\n"
            f"目标读者：{audience}\n"
            f"{revision_hint}\n"
            f"{existing_hint}"
            "要求：\n"
            "1. 文案适合人工复审后直接发布。\n"
            "2. 标签控制在 8-12 个。\n"
            "3. 封面标题不超过 16 个字。\n"
            "4. 不能承诺自动发帖或绕过平台风控。\n"
        )
        return client.chat_json(system, user, temperature=0.7)

    # stub 数据
    payload = {
        "positioning": f"面向 {audience} 的教育自媒体效率提升内容",
        "cover_title": "AI 帮你省下内容时间",
        "cover_prompt": f"创作一张手绘风格的信息图卡片，比例为 3:4 竖版，背景为带有纸质肌理的米色，主题是：{topic}，风格清爽、专业、适合教育行业运营者。卡片上方以红黑相间的毛笔字体突出标题。",
        "hashtags": [
            "教育行业AI", "自媒体运营", "公众号运营", "小红书运营",
            "AI提效", "内容自动化", "教培增长", "运营提效",
        ],
        "publish_checklist": [
            "确认文案不涉及夸张承诺",
            "检查封面文案和正文观点一致",
            "人工核对案例和数据",
            "最终由人工登录小红书完成发布",
        ],
        "variants": [
            {
                "title": "教培团队，真的别再手写所有内容了",
                "body": "每天从选题到配图都手搓，团队一定会被重复劳动拖住。首期最值得做的是把选题、大纲、文案初稿和素材包交给 AI，最后保留人工审核和发布。",
                "angle": "痛点切入",
            },
            {
                "title": "为什么我建议教培机构先做素材包，不急着自动发帖",
                "body": "不是做不到，而是没必要一上来就冒风控风险。先把三版文案、标签建议、封面标题和封面图 prompt 交给 AI，人工过一遍再发，效率和安全性都更稳。",
                "angle": "策略拆解",
            },
            {
                "title": "AI 自动化第一阶段，教育团队先打通这 2 个场景",
                "body": "公众号负责沉淀深度内容，小红书负责高频曝光。只要先跑通这两个场景，后面再往私域回复和视频处理扩展，整个内容系统就有了雏形。",
                "angle": "行动建议",
            },
        ],
    }
    if revision_mode:
        payload = revise_stub_payload(
            payload if existing_payload is None else existing_payload,
            revision_mode,
            revision_notes=revision_notes,
            revision_scope=revision_scope,
        )
    return payload


def format_card_content(payload: dict[str, Any], variant_index: int = 0) -> str:
    """将素材包格式化为飞书卡片 Markdown 内容。"""
    v = payload["variants"][variant_index]
    tags_str = " ".join(f"#{t}" for t in payload["hashtags"][:6])
    content = (
        f"**📌 标题：** {v['title']}\n\n"
        f"**✨ 切入角度：** {v['angle']}\n\n"
        f"**📝 正文：**\n{v['body']}\n\n"
        f"**🏷️ 标签：** {tags_str}"
    )
    return content


def format_full_content(payload: dict[str, Any]) -> str:
    """格式化完整文案（最终稿卡片用）。"""
    lines = [f"**📌 封面标题：** {payload['cover_title']}\n"]
    for i, v in enumerate(payload["variants"], 1):
        lines.append(f"**━━━ 版本 {i}：{v['title']} ━━━**")
        lines.append(f"**切入角度：** {v['angle']}")
        lines.append(f"{v['body']}\n")
    tags_str = " ".join(f"#{t}" for t in payload["hashtags"])
    lines.append(f"**🏷️ 标签：** {tags_str}")
    return "\n".join(lines)


def _review_index_dir() -> Path:
    return ensure_dir(OUTPUT_DIR / "xhs_review_index")


def _review_index_path(message_id: str) -> Path:
    return _review_index_dir() / f"{message_id}.json"


def save_review_state(run_dir: Path, state: dict[str, Any]) -> None:
    save_json_file(run_dir / "review_state.json", state)
    message_id = state.get("current_review_message_id")
    if message_id:
        save_json_file(_review_index_path(str(message_id)), {"run_dir": str(run_dir)})


def load_review_state(message_id: str) -> tuple[Path, dict[str, Any]]:
    index_path = _review_index_path(message_id)
    if not index_path.exists():
        raise FileNotFoundError(f"找不到卡片状态索引: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    run_dir = Path(index["run_dir"])
    state_path = run_dir / "review_state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"找不到审核状态文件: {state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return run_dir, state


def revise_stub_payload(
    base_payload: dict[str, Any],
    revision_mode: str,
    revision_notes: str | None = None,
    revision_scope: str | None = None,
) -> dict[str, Any]:
    payload = deepcopy(base_payload)
    note_suffix = ""
    if revision_notes:
        short_notes = revision_notes.strip().replace("\n", " ")
        if len(short_notes) > 60:
            short_notes = short_notes[:60] + "..."
        note_suffix = f"（修改说明：{short_notes}）"
    scope_suffix = f"【范围：{revision_scope}】" if revision_scope else ""
    if revision_mode == "modify":
        payload["cover_title"] = f"{payload['cover_title']} · 修改版{scope_suffix}"
        payload["cover_prompt"] = f"{payload['cover_prompt']} 这一版更强调钩子和结构优化。{note_suffix}"
        payload["variants"] = [
            {
                **variant,
                "title": f"修改版｜{variant['title']}",
                "body": f"{variant['body']} 这一版更聚焦开头钩子和可读性。{note_suffix}",
            }
            for variant in payload["variants"]
        ]
    elif revision_mode == "rewrite":
        payload["cover_title"] = f"AI 提效新视角{scope_suffix}"
        payload["cover_prompt"] = (
            "创作一张手绘风格的信息图卡片，比例为 3:4 竖版，背景为米白色纸感，"
            "主题围绕教育自媒体 AI 自动化提效，风格更干净、更有新鲜感。"
            f"{note_suffix}"
        )
        payload["variants"] = [
            {
                "title": "别再把内容运营当成纯体力活了",
                "body": "如果团队每天都在重复写选题、改标题、找配图，那就说明内容流程已经该升级了。先把最耗时的部分交给 AI，再保留人工审核，效率会更稳。"
                f"{note_suffix}",
                "angle": "流程重构",
            },
            {
                "title": "小红书先做素材包，为什么更适合教培团队",
                "body": "对教育行业来说，先把文案、标签、封面和检查清单做成标准件，能更快建立内容生产节奏。自动发帖不是第一步，先稳住素材质量更重要。"
                f"{note_suffix}",
                "angle": "方法升级",
            },
            {
                "title": "AI 内容自动化，第一阶段就该这样拆",
                "body": "公众号负责沉淀深度内容，小红书负责高频种草，两边都先跑通素材生成和人工审核，再考虑扩展到更复杂的自动化环节。"
                f"{note_suffix}",
                "angle": "落地路径",
            },
        ]
    return payload


def _review_image_template_state(image_templates: dict[str, Any] | None = None) -> dict[str, str]:
    state = dict(DEFAULT_REVIEW_IMAGE_TEMPLATES)
    if image_templates:
        for key in ("cover_template_key", "graphics_template_key"):
            value = image_templates.get(key)
            if value:
                state[key] = str(value)
    return state


def _build_review_prompt_state(image_templates: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"image_templates": _review_image_template_state(image_templates)}


def _normalize_optional_path(path: str | Path | None) -> str | None:
    if path in {None, ""}:
        return None
    return str(Path(path).expanduser())


def _normalize_optional_paths(paths: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized: list[str] = []
    for path in list(paths or []):
        resolved = _normalize_optional_path(path)
        if resolved:
            normalized.append(resolved)
    return normalized


def _current_template_family(image_templates: dict[str, Any] | None, key: str) -> str:
    state = _review_image_template_state(image_templates)
    return state[key]


def _render_prompt_image(
    prompt: str,
    target_path: Path,
    config: dict[str, Any],
    dry_run: bool,
    skip_image: bool,
) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if skip_image or dry_run:
        _generate_placeholder(target_path, prompt)
        return target_path
    return generate_image(
        prompt,
        target_path,
        config,
        allow_placeholder=False,
    )


def _render_prompt_cover(
    run_dir: Path,
    payload: dict[str, Any],
    config: dict[str, Any],
    dry_run: bool,
    skip_image: bool,
    image_templates: dict[str, Any] | None = None,
    refresh_index: int = 0,
    current_cover_path: str | None = None,
) -> Path:
    prompt_state = _build_review_prompt_state(image_templates)
    prompt = build_cover_prompt(payload, prompt_state, DEFAULT_REVIEW_CLIENT_SLUG)
    fallback_path = run_dir / "slides" / "slide_1.png"
    target_path = (
        _versioned_artifact_path(current_cover_path, fallback_path, "refresh", refresh_index)
        if refresh_index
        else fallback_path
    )
    return _render_prompt_image(prompt, target_path, config, dry_run, skip_image)


def _render_overlay_cover(
    run_dir: Path,
    payload: dict[str, Any],
    image_templates: dict[str, Any] | None,
    base_image_path: str,
    refresh_index: int = 0,
    current_cover_path: str | None = None,
) -> Path:
    fallback_path = run_dir / "slides" / "slide_1.png"
    target_path = (
        _versioned_artifact_path(current_cover_path, fallback_path, "refresh", refresh_index)
        if refresh_index
        else fallback_path
    )
    variants = payload.get("variants") or []
    selling_points = extract_sentences(str((variants[0] or {}).get("body") or ""), 3) if variants else []
    sub_title = str((variants[0] or {}).get("angle") or "") if variants else ""
    templates = load_image_prompt_templates(DEFAULT_REVIEW_CLIENT_SLUG)
    cover_templates = templates.get("cover_templates") or {}
    family = _current_template_family(image_templates, "cover_template_key")
    template = cover_templates.get(family) or {}
    return render_base_image_overlay(
        base_image_path=base_image_path,
        output_path=target_path,
        template_family=family,
        main_title=str(payload.get("cover_title") or payload.get("title") or ""),
        sub_title=sub_title or str(template.get("sub_title_hint") or ""),
        selling_points=selling_points,
        cta_text=str(template.get("cta_text") or "点击咨询领取专属方案"),
    )


def _render_prompt_graphics(
    run_dir: Path,
    payload: dict[str, Any],
    config: dict[str, Any],
    dry_run: bool,
    skip_image: bool,
    image_templates: dict[str, Any] | None = None,
    refresh_index: int = 0,
    current_graphic_paths: list[str] | None = None,
) -> list[Path]:
    prompt_state = _build_review_prompt_state(image_templates)
    graphic_prompts = build_graphic_prompts(payload, prompt_state, DEFAULT_REVIEW_CLIENT_SLUG)[:2]
    current_graphic_paths = list(current_graphic_paths or [])
    rendered_paths: list[Path] = []
    for index, (_, prompt) in enumerate(graphic_prompts, start=2):
        fallback_path = run_dir / "slides" / f"slide_{index}.png"
        current_path = current_graphic_paths[index - 2] if index - 2 < len(current_graphic_paths) else None
        target_path = (
            _versioned_artifact_path(current_path, fallback_path, "refresh", refresh_index)
            if refresh_index
            else fallback_path
        )
        rendered_paths.append(_render_prompt_image(prompt, target_path, config, dry_run, skip_image))
    return rendered_paths


def _render_overlay_graphics(
    run_dir: Path,
    payload: dict[str, Any],
    image_templates: dict[str, Any] | None,
    graphic_base_image_paths: list[str],
    refresh_index: int = 0,
    current_graphic_paths: list[str] | None = None,
) -> list[Path]:
    templates = load_image_prompt_templates(DEFAULT_REVIEW_CLIENT_SLUG)
    family = _current_template_family(image_templates, "graphics_template_key")
    graphics_templates = templates.get("graphics_templates") or {}
    template = graphics_templates.get(family) or {}
    variants = payload.get("variants") or []
    current_graphic_paths = list(current_graphic_paths or [])
    rendered_paths: list[Path] = []

    for index, base_path in enumerate(graphic_base_image_paths[:2], start=2):
        fallback_path = run_dir / "slides" / f"slide_{index}.png"
        current_path = current_graphic_paths[index - 2] if index - 2 < len(current_graphic_paths) else None
        target_path = (
            _versioned_artifact_path(current_path, fallback_path, "refresh", refresh_index)
            if refresh_index
            else fallback_path
        )
        variant = variants[index - 2] if index - 2 < len(variants) else {}
        rendered_paths.append(
            render_base_image_overlay(
                base_image_path=base_path,
                output_path=target_path,
                template_family=family,
                main_title=str(variant.get("title") or payload.get("cover_title") or ""),
                sub_title=str(variant.get("angle") or payload.get("cover_title") or ""),
                selling_points=extract_sentences(str(variant.get("body") or ""), 4),
                trust_points=extract_sentences(str(variant.get("body") or ""), 4),
                cta_text=str(template.get("cta_text") or "点击咨询专属提升方案"),
            )
        )
    return rendered_paths


def _render_prompt_slide_set(
    run_dir: Path,
    payload: dict[str, Any],
    config: dict[str, Any],
    dry_run: bool,
    skip_image: bool,
    image_templates: dict[str, Any] | None = None,
    marker: str = "rev",
    version_index: int = 0,
    current_slide_paths: list[str] | None = None,
) -> list[Path]:
    prompt_state = _build_review_prompt_state(image_templates)
    cover_prompt = build_cover_prompt(payload, prompt_state, DEFAULT_REVIEW_CLIENT_SLUG)
    graphic_prompts = build_graphic_prompts(payload, prompt_state, DEFAULT_REVIEW_CLIENT_SLUG)[:2]
    current_slide_paths = list(current_slide_paths or [])

    rendered_paths: list[Path] = []
    prompts: list[str] = [cover_prompt, *(prompt for _, prompt in graphic_prompts)]
    for index, prompt in enumerate(prompts, start=1):
        fallback_path = run_dir / "slides" / f"slide_{index}.png"
        current_path = current_slide_paths[index - 1] if index - 1 < len(current_slide_paths) else None
        target_path = (
            _versioned_artifact_path(current_path, fallback_path, marker, version_index)
            if version_index
            else fallback_path
        )
        rendered_paths.append(_render_prompt_image(prompt, target_path, config, dry_run, skip_image))
    return rendered_paths


def _render_mixed_slide_set(
    run_dir: Path,
    payload: dict[str, Any],
    config: dict[str, Any],
    dry_run: bool,
    skip_image: bool,
    image_templates: dict[str, Any] | None = None,
    cover_base_image_path: str | None = None,
    graphic_base_image_paths: list[str] | None = None,
    marker: str = "rev",
    version_index: int = 0,
    current_slide_paths: list[str] | None = None,
) -> list[Path]:
    current_slide_paths = list(current_slide_paths or [])
    cover_current = current_slide_paths[0] if current_slide_paths else None
    graphic_current = current_slide_paths[1:] if len(current_slide_paths) > 1 else []

    cover_path = (
        _render_overlay_cover(
            run_dir=run_dir,
            payload=payload,
            image_templates=image_templates,
            base_image_path=cover_base_image_path,
            refresh_index=version_index if marker != "init" else 0,
            current_cover_path=cover_current,
        )
        if cover_base_image_path
        else _render_prompt_cover(
            run_dir=run_dir,
            payload=payload,
            config=config,
            dry_run=dry_run,
            skip_image=skip_image,
            image_templates=image_templates,
            refresh_index=version_index if marker != "init" else 0,
            current_cover_path=cover_current,
        )
    )

    overlay_graphics = _render_overlay_graphics(
        run_dir=run_dir,
        payload=payload,
        image_templates=image_templates,
        graphic_base_image_paths=_normalize_optional_paths(graphic_base_image_paths),
        refresh_index=version_index if marker != "init" else 0,
        current_graphic_paths=graphic_current,
    )
    graphics: list[Path] = list(overlay_graphics)
    if len(graphics) < 2:
        prompt_graphics = _render_prompt_graphics(
            run_dir=run_dir,
            payload=payload,
            config=config,
            dry_run=dry_run,
            skip_image=skip_image,
            image_templates=image_templates,
            refresh_index=version_index if marker != "init" else 0,
            current_graphic_paths=graphic_current,
        )
        graphics.extend(prompt_graphics[len(graphics):2])

    return [cover_path, *graphics]


def generate_slide_images(
    run_dir: Path,
    payload: dict[str, Any],
    topic_data: dict[str, Any] | None,
    config: dict[str, Any],
    dry_run: bool,
    skip_image: bool,
    image_templates: dict[str, Any] | None = None,
    cover_base_image_path: str | None = None,
    graphic_base_image_paths: list[str] | None = None,
) -> list[Path]:
    """生成多张幻灯片图片。

    默认使用武汉教培客户的 prompt 模板，输出 1 张宣传封面图 + 2 张内容配图。
    只有旧状态才允许回退到 HTML 视觉卡片路径；新 prompt 模板链路失败时直接报错，
    避免把错图静默发出去。
    """
    del topic_data
    try:
        print("  🧠 渲染引擎: 客户 prompt 模板 (cover + graphics)")
        images = _render_mixed_slide_set(
            run_dir=run_dir,
            payload=payload,
            config=config,
            dry_run=dry_run,
            skip_image=skip_image,
            image_templates=image_templates,
            cover_base_image_path=_normalize_optional_path(cover_base_image_path),
            graphic_base_image_paths=_normalize_optional_paths(graphic_base_image_paths),
            marker="init",
            version_index=0,
        )
        print(f"  ✅ {len(images)} 张幻灯片已生成")
        return images
    except Exception as e:
        if image_templates:
            print(f"  ❌ prompt 渲染失败: {e}")
            raise
        print(f"  ⚠️  prompt 渲染失败 ({e})，回退到 HTML 卡片模板")

    style_hint = "info_card"
    slide_topics = _build_payload_slide_topics(payload, style_hint)
    images = [
        render_image(topic, run_dir / "slides" / f"slide_{index}.png")
        for index, topic in enumerate(slide_topics, start=1)
    ]
    print(f"  ✅ {len(images)} 张幻灯片已生成")
    return images


def upload_slide_images(
    image_paths: list[Path], config: dict[str, Any], dry_run: bool
) -> list[str]:
    """上传多张图片到飞书，返回 image_key 列表。"""
    if dry_run:
        return [f"img_dry_run_{i}" for i in range(len(image_paths))]
    feishu = FeishuClient(config)
    return feishu.upload_images(image_paths)


# 保持向后兼容
def generate_cover_art(run_dir, payload, config, dry_run, skip_image):
    images = generate_slide_images(run_dir, payload, None, config, dry_run, skip_image)
    return images[0]

def upload_cover_image(cover_path, config, dry_run):
    keys = upload_slide_images([cover_path], config, dry_run)
    return keys[0]


def send_revision_request(
    run_dir: Path,
    state: dict[str, Any],
    action: str,
    config: dict[str, Any],
    dry_run: bool,
) -> str:
    """发送修改/重写说明卡，等待用户补充修改意见。"""
    payload = state["payload"]
    note_id = state.get("note_id", run_dir.name)
    tags_str = " ".join(f"#{t}" for t in payload["hashtags"][:6])
    card_content = format_card_content(payload, 0)

    if dry_run:
        message_id = f"msg_edit_{action}_{run_dir.name}"
        print("\n📋 修改说明卡预览（dry-run）...")
        print(f"  标题: ✏️ {('修改' if action == 'modify' else '重写')}说明 — {payload['cover_title']}")
        print(f"  内容:\n{card_content}")
        print(f"  标签: {tags_str}")
    else:
        feishu = FeishuClient(config)
        message_id = feishu.send_revision_request_card(
            image_key=state["image_key"],
            title=payload["cover_title"],
            content=card_content,
            tags=tags_str,
            note_id=note_id,
            revision_mode=action,
        )
        print(f"  ✅ 修改说明卡已发送: {message_id}")
        print("  ⏸️  已暂停，等待你在卡片里填写修改说明后再继续。")

    state["status"] = "waiting_revision_notes"
    state["current_review_message_id"] = message_id
    state["last_action"] = action
    state["pending_revision_mode"] = action
    state["revision_request_at"] = timestamp()
    save_review_state(run_dir, state)
    return message_id


def load_revision_notes_from_file(path_str: str | None) -> tuple[str | None, str | None]:
    """读取修改说明文件，返回 (revision_notes, revision_scope)。"""
    if not path_str:
        return None, None
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"修改说明文件不存在: {path}")
    if path.suffix.lower() in {".json", ".yaml", ".yml"}:
        data = json.loads(path.read_text(encoding="utf-8")) if path.suffix.lower() == ".json" else None
        if data is None:
            from common import load_yaml_file

            data = load_yaml_file(path)
        return (
            str(data.get("revision_notes") or data.get("notes") or "").strip() or None,
            str(data.get("revision_scope") or data.get("scope") or "").strip() or None,
        )
    text = path.read_text(encoding="utf-8").strip()
    return (text or None, None)


def request_revision_notes(
    action: str,
    message_id: str,
    dry_run: bool = False,
    config_path: str | None = None,
) -> dict[str, Any]:
    """将当前审核卡切换为“修改说明卡”，等待用户补充修改意见。"""
    if action not in {"modify", "rewrite"}:
        raise ValueError("request_revision_notes 仅支持 modify/rewrite")
    try:
        run_dir, state = load_review_state(message_id)
    except FileNotFoundError as e:
        return _blocked_missing_review_state(action, message_id, e)
    current_message_id = state.get("current_review_message_id")
    if current_message_id != message_id:
        print(
            f"  ⚠️  该卡片已过期：当前卡片是 {current_message_id}，"
            f"收到的是 {message_id}"
        )
        result = {
            "status": "stale",
            "task_dir": str(run_dir),
            "steps": {
                "stale_review_card": message_id,
                "current_review_card": current_message_id,
            },
        }
        _save_result(run_dir, result)
        return result

    effective_dry_run = dry_run or bool(state.get("dry_run", False))
    config = {} if effective_dry_run else load_config(config_path)
    topic = state["topic"]
    audience = state["audience"]
    print("=" * 60)
    print("🚀 小红书 + 飞书修改说明")
    print(f"   主题：{topic}")
    print(f"   受众：{audience}")
    print(f"   动作：{action}")
    print(f"   模式：{'dry-run（本地测试）' if effective_dry_run else '真实运行'}")
    print("=" * 60)

    new_message_id = send_revision_request(run_dir, state, action, config, effective_dry_run)

    result = {
        "status": "waiting_revision_notes",
        "task_dir": str(run_dir),
        "steps": {
            "action": action,
            "revision_request_card": new_message_id,
        },
    }
    _save_result(run_dir, result)
    print("\n" + "=" * 60)
    print("🎉 已切换到修改说明卡，等待你填写修改意见")
    print(f"   任务目录: {run_dir}")
    print(f"   修改说明卡: {new_message_id}")
    print("=" * 60)
    return result


# ── 主流程 ─────────────────────────────────────────────────

def _match_topic_data(topic: str) -> dict[str, Any] | None:
    """尝试从预设选题库中匹配选题，返回选题数据。"""
    matched = get_topic_by_title(topic)
    if matched:
        print(f"  📚 匹配到预设选题: {matched['title']} (style={matched['style']})")
    return matched


def _review_card_title(payload: dict[str, Any]) -> str:
    return f"🎨 小红书笔记审核 — {payload['cover_title']}"


def _review_card_tags(payload: dict[str, Any]) -> str:
    return " ".join(f"#{t}" for t in payload["hashtags"][:6])


def _persisted_review_style_hint(state: dict[str, Any]) -> str | None:
    style = state.get("topic_data_style")
    if style:
        return str(style)
    return None


def _persisted_image_templates(state: dict[str, Any]) -> dict[str, str] | None:
    templates = state.get("image_templates")
    if isinstance(templates, dict) and any(templates.get(key) for key in ("cover_template_key", "graphics_template_key")):
        return _review_image_template_state(templates)
    return None


def _normalized_slide_paths(run_dir: Path, state: dict[str, Any]) -> list[str]:
    slide_paths = [str(path) for path in state.get("slide_paths") or [] if path]
    if slide_paths:
        return slide_paths
    cover_path = state.get("cover_path")
    if cover_path:
        return [str(cover_path)]
    return [str(run_dir / "cover.png")]


def _normalized_image_keys(state: dict[str, Any]) -> list[str]:
    image_keys = [str(key) for key in state.get("image_keys") or [] if key]
    if image_keys:
        return image_keys
    image_key = state.get("image_key")
    if image_key:
        return [str(image_key)]
    return []


def _refreshed_artifact_path(
    current_path: str | Path | None,
    fallback_path: Path,
    refresh_index: int,
) -> Path:
    base_path = Path(current_path) if current_path else fallback_path
    suffix = base_path.suffix or ".png"
    return base_path.with_name(f"{base_path.stem}_refresh_{refresh_index}{suffix}")


def _versioned_artifact_path(
    current_path: str | Path | None,
    fallback_path: Path,
    marker: str,
    version_index: int,
) -> Path:
    base_path = Path(current_path) if current_path else fallback_path
    suffix = base_path.suffix or ".png"
    return base_path.with_name(f"{base_path.stem}_{marker}_{version_index}{suffix}")


def _split_review_points(text: str | None, limit: int = 3) -> list[str]:
    raw = str(text or "").replace("\n", "。")
    parts = [part.strip(" 。！？!?；;") for part in re.split(r"[。！？!?；;]+", raw) if part.strip(" 。！？!?；;")]
    return parts[:limit]


def _variant_review_points(payload: dict[str, Any], variant: dict[str, Any], limit: int = 3) -> list[str]:
    points = _split_review_points(str(variant.get("body") or ""), limit=limit)
    if points:
        return points
    title = str(variant.get("title") or payload.get("cover_title") or "").strip()
    if title:
        return [title]
    return ["内容待确认"]


def _content_layout_style(style_hint: str | None) -> str:
    if style_hint in {"data_table", "info_card", "comparison", "timeline"}:
        return str(style_hint)
    return "info_card"


def _build_payload_cover_topic(payload: dict[str, Any], style_hint: str | None) -> dict[str, Any]:
    variants = payload.get("variants") or []
    lead_variant = variants[0] if variants else {}
    return {
        "title": payload.get("cover_title") or lead_variant.get("title") or "",
        "subtitle": lead_variant.get("angle") or "",
        "style": "promo_cover",
        "original_style": _content_layout_style(style_hint),
        "tags": list(payload.get("hashtags") or []),
        "selling_points": _variant_review_points(payload, lead_variant, limit=3),
    }


def _build_payload_content_topic(
    payload: dict[str, Any],
    variant: dict[str, Any],
    style_hint: str | None,
    paired_variant: dict[str, Any] | None = None,
) -> dict[str, Any]:
    title = str(variant.get("title") or payload.get("cover_title") or "")
    subtitle = str(variant.get("angle") or payload.get("cover_title") or "")
    tags = list(payload.get("hashtags") or [])
    points = _variant_review_points(payload, variant, limit=3)
    style = _content_layout_style(style_hint)

    if style == "data_table":
        return {
            "title": title,
            "subtitle": subtitle,
            "style": "data_table",
            "tags": tags,
            "data_content": {
                "table_title": subtitle or title,
                "headers": ["模块", "说明"],
                "rows": [[f"要点{i + 1}", point] for i, point in enumerate(points)],
            },
        }

    if style == "comparison":
        other = paired_variant or variant
        other_points = _variant_review_points(payload, other, limit=3)
        item_count = max(len(points), len(other_points), 1)
        items = []
        for i in range(item_count):
            items.append(
                {
                    "left": points[i] if i < len(points) else "",
                    "right": other_points[i] if i < len(other_points) else "",
                    "label": f"要点{i + 1}",
                }
            )
        return {
            "title": title,
            "subtitle": subtitle,
            "style": "comparison",
            "tags": tags,
            "compare_data": {
                "left_title": title or "当前版本",
                "right_title": str(other.get("title") or "补充说明"),
                "items": items,
            },
        }

    if style == "timeline":
        return {
            "title": title,
            "subtitle": subtitle,
            "style": "timeline",
            "tags": tags,
            "timeline_data": [
                {
                    "month": f"步骤{i + 1}",
                    "title": point if len(point) <= 18 else f"步骤{i + 1}",
                    "desc": point,
                }
                for i, point in enumerate(points)
            ],
        }

    return {
        "title": title,
        "subtitle": subtitle,
        "style": "info_card",
        "tags": tags,
        "key_points": points,
    }


def _build_payload_slide_topics(payload: dict[str, Any], style_hint: str | None) -> list[dict[str, Any]]:
    variants = list(payload.get("variants") or [])
    if not variants:
        fallback_variant = {
            "title": payload.get("cover_title") or "",
            "angle": "",
            "body": "",
        }
        variants = [fallback_variant]

    first_variant = variants[0]
    second_variant = variants[1] if len(variants) > 1 else first_variant
    third_variant = variants[2] if len(variants) > 2 else second_variant

    return [
        _build_payload_cover_topic(payload, style_hint),
        _build_payload_content_topic(payload, first_variant, style_hint, paired_variant=second_variant),
        _build_payload_content_topic(payload, third_variant, style_hint, paired_variant=first_variant),
    ]


def _render_payload_slide_set(
    run_dir: Path,
    payload: dict[str, Any],
    style_hint: str | None,
    marker: str,
    version_index: int,
    current_slide_paths: list[str] | None = None,
) -> list[Path]:
    topics = _build_payload_slide_topics(payload, style_hint)
    current_slide_paths = list(current_slide_paths or [])
    rendered: list[Path] = []
    for index, topic in enumerate(topics, start=1):
        fallback = run_dir / "slides" / f"slide_{index}.png"
        current_path = current_slide_paths[index - 1] if index - 1 < len(current_slide_paths) else None
        target = _versioned_artifact_path(current_path, fallback, marker, version_index)
        rendered.append(render_image(topic, target))
    return rendered


def _render_refreshed_cover(
    run_dir: Path,
    payload: dict[str, Any],
    style_hint: str | None,
    config: dict[str, Any],
    dry_run: bool,
    skip_image: bool,
    refresh_index: int,
    current_cover_path: str | None,
) -> Path:
    target_path = _versioned_artifact_path(
        current_cover_path,
        run_dir / "cover.png",
        "refresh",
        refresh_index,
    )
    if style_hint:
        return render_image(_build_payload_slide_topics(payload, style_hint)[0], target_path)
    if skip_image or dry_run:
        _generate_placeholder(target_path, payload.get("cover_prompt", ""))
        return target_path
    return generate_image(
        payload["cover_prompt"],
        target_path,
        config,
        allow_placeholder=False,
    )


def _render_refreshed_graphics(
    run_dir: Path,
    payload: dict[str, Any],
    style_hint: str,
    refresh_index: int,
    current_graphic_paths: list[str],
) -> list[Path]:
    slide_topics = _build_payload_slide_topics(payload, style_hint)[1:]
    if not current_graphic_paths:
        current_graphic_paths = [
            str(run_dir / "slides" / "slide_2.png"),
            str(run_dir / "slides" / "slide_3.png"),
        ]
    if len(current_graphic_paths) > len(slide_topics):
        raise ValueError("当前任务的独立内容配图数量超出可刷新范围")

    refreshed_paths: list[Path] = []
    for index, topic in enumerate(slide_topics[: len(current_graphic_paths)]):
        fallback = run_dir / "slides" / f"slide_{index + 2}.png"
        target_path = _versioned_artifact_path(
            current_graphic_paths[index] if index < len(current_graphic_paths) else None,
            fallback,
            "refresh",
            refresh_index,
        )
        refreshed_paths.append(render_image(topic, target_path))
    return refreshed_paths


def _send_review_card(
    payload: dict[str, Any],
    image_keys: list[str],
    note_id: str,
    config: dict[str, Any],
    dry_run: bool,
    message_suffix: str,
) -> str:
    card_content = format_card_content(payload, 0)
    tags_str = _review_card_tags(payload)
    if dry_run:
        message_id = f"msg_{message_suffix}"
        print("  ⏭️  dry-run 模式，跳过发送新审核卡")
        print(f"  新卡片内容:\n{card_content}")
        return message_id

    feishu = FeishuClient(config)
    message_id = feishu.send_review_card(
        image_key=image_keys,
        title=_review_card_title(payload),
        content=card_content,
        tags=tags_str,
        note_id=note_id,
    )
    print(f"  ✅ 新审核卡片已发送: {message_id}")
    print("  ⏸️  已停在新初稿阶段，等你继续点通过或刷新图片。")
    return message_id


def _blocked_image_refresh(
    run_dir: Path,
    state: dict[str, Any],
    action: str,
    reason: str,
    message: str,
) -> dict[str, Any]:
    print(f"  ⚠️  {message}")
    state["review_action_mode"] = "image_refresh"
    state["last_action"] = action
    state["pending_revision_mode"] = None
    save_review_state(run_dir, state)

    result = {
        "status": "blocked",
        "reason": reason,
        "message": message,
        "task_dir": str(run_dir),
        "steps": {
            "action": action,
            "reason": reason,
        },
    }
    _save_result(run_dir, result)
    return result


def _blocked_missing_review_state(action: str, message_id: str, error: Exception) -> dict[str, Any]:
    message = f"找不到卡片状态索引，无法继续处理: {error}"
    print(f"  ⚠️  {message}")
    return {
        "status": "blocked",
        "reason": "missing_review_state",
        "message": message,
        "task_dir": None,
        "steps": {
            "action": action,
            "message_id": message_id,
        },
    }


def _validate_multi_image_review_state(
    run_dir: Path,
    state: dict[str, Any],
    action: str,
    slide_paths: list[str],
    image_keys: list[str],
) -> dict[str, Any] | None:
    if max(len(slide_paths), len(image_keys)) <= 1:
        return None
    if len(image_keys) == len(slide_paths):
        return None
    return _blocked_image_refresh(
        run_dir,
        state,
        action,
        reason="inconsistent_review_state",
        message="当前审核状态的图片路径与飞书 image_keys 数量不一致，无法安全刷新图片。",
    )


def run_flow(
    topic: str,
    audience: str,
    dry_run: bool = False,
    skip_image: bool = False,
    auto_approve: bool = False,
    config_path: str | None = None,
    base_image_path: str | None = None,
    graphic_base_image_paths: list[str] | None = None,
) -> dict[str, Any]:
    """执行初稿阶段：生成素材包 + 多图渲染、发审核卡、保存状态后暂停。"""

    config = {} if dry_run else load_config(config_path)
    result = {"status": "running", "steps": {}}

    print("=" * 60)
    print("🚀 小红书 + 飞书初稿流程 v3.0")
    print(f"   主题：{topic}")
    print(f"   受众：{audience}")
    print(f"   模式：{'dry-run（本地测试）' if dry_run else '真实运行'}")
    print("=" * 60)

    run_dir = make_run_dir("xhs_feishu", topic)
    result["task_dir"] = str(run_dir)

    # ── Step 0: 匹配预设选题 ────────────────────────────────
    topic_data = _match_topic_data(topic)

    # ── Step 1: 生成素材包 ──────────────────────────────────
    print("\n📦 步骤 1/4：生成小红书素材包...")
    try:
        # 如果匹配到预设选题，用选题里的标签和标题
        if topic_data:
            payload = generate_xhs_payload(topic, audience, config, dry_run)
            payload["hashtags"] = topic_data.get("tags", payload["hashtags"])
            payload["cover_title"] = topic_data.get("title", payload["cover_title"])
        else:
            payload = generate_xhs_payload(topic, audience, config, dry_run)
    except Exception as e:
        print(f"  ❌ 素材包生成失败: {e}")
        result["status"] = "failed"
        result["error"] = f"素材包生成失败: {e}"
        _save_result(run_dir, result)
        return result
    review_image_templates = _review_image_template_state()
    cover_base_image_path = _normalize_optional_path(base_image_path)
    graphic_base_image_paths = _normalize_optional_paths(graphic_base_image_paths)

    save_json_file(run_dir / "payload.json", payload)
    print(f"  ✅ 素材包已生成，{len(payload['variants'])} 个版本")
    print(f"  📁 任务目录: {run_dir}")
    result["steps"]["payload"] = str(run_dir / "payload.json")

    # 保存各文件
    save_text_file(run_dir / "cover_title.txt", payload["cover_title"] + "\n")
    save_text_file(run_dir / "cover_prompt.txt", payload.get("cover_prompt", "") + "\n")
    for i, v in enumerate(payload["variants"], 1):
        save_text_file(
            run_dir / f"variant_{i}.md",
            f"# {v['title']}\n\n**角度：** {v['angle']}\n\n{v['body']}\n",
        )

    # ── Step 2: 生成多张幻灯片图片 ───────────────────────────
    print("\n🎨 步骤 2/4：生成图片（多图模式）...")
    try:
        slide_paths = generate_slide_images(
            run_dir,
            payload,
            topic_data,
            config,
            dry_run,
            skip_image,
            image_templates=review_image_templates,
            cover_base_image_path=cover_base_image_path,
            graphic_base_image_paths=graphic_base_image_paths,
        )
    except (GeminiImageError, Exception) as e:
        print(f"  ❌ 图片生成失败: {e}")
        result["status"] = "failed"
        result["error"] = f"图片生成失败: {e}"
        _save_result(run_dir, result)
        return result
    result["steps"]["slides"] = [str(p) for p in slide_paths]
    result["steps"]["slide_count"] = len(slide_paths)

    # ── Step 3: 上传飞书 ────────────────────────────────────
    print(f"\n☁️  步骤 3/4：上传 {len(slide_paths)} 张图片到飞书...")
    try:
        image_keys = upload_slide_images(slide_paths, config, dry_run)
        if dry_run:
            print("  ⏭️  dry-run 模式，跳过上传")
        else:
            print(f"  ✅ 上传成功: {len(image_keys)} 张")
        result["steps"]["upload"] = image_keys
    except Exception as e:
        print(f"  ❌ 上传失败: {e}")
        result["status"] = "failed"
        result["error"] = f"上传失败: {e}"
        _save_result(run_dir, result)
        return result

    # ── Step 4: 发送审核卡片（多图） ──────────────────────────
    card_content = format_card_content(payload, 0)
    tags_str = " ".join(f"#{t}" for t in payload["hashtags"][:6])
    note_id = run_dir.name

    if dry_run:
        print("\n📋 步骤 4/4：发送审核卡片到飞书...")
        print("  ⏭️  dry-run 模式，跳过发送")
        print(f"\n  ── 审核卡片预览 ──")
        print(f"  标题: 🎨 小红书笔记审核 — {payload['cover_title']}")
        print(f"  图片: {len(image_keys)} 张")
        print(f"  内容:\n{card_content}")
        print(f"  标签: {tags_str}")
        message_id = f"msg_dry_run_{run_dir.name}"
    else:
        print("\n📋 步骤 4/4：发送审核卡片到飞书...")
        try:
            feishu = FeishuClient(config)
            message_id = feishu.send_review_card(
                image_key=image_keys,
                title=f"🎨 小红书笔记审核 — {payload['cover_title']}",
                content=card_content,
                tags=tags_str,
                note_id=note_id,
            )
            print(f"  ✅ 审核卡片已发送: {message_id} ({len(image_keys)}图)")
            print("  ⏸️  已暂停在初稿审核阶段，等你点通过或刷新图片后再继续。")
        except Exception as e:
            print(f"  ❌ 发送审核卡片失败: {e}")
            result["status"] = "failed"
            result["error"] = f"发送审核卡片失败: {e}"
            _save_result(run_dir, result)
            return result

    state = {
        "status": "waiting_review",
        "topic": topic,
        "audience": audience,
        "dry_run": dry_run,
        "skip_image": skip_image,
        "payload": payload,
        "slide_paths": [str(p) for p in slide_paths],
        "image_keys": image_keys,
        "image_templates": review_image_templates,
        "cover_base_image_path": cover_base_image_path,
        "graphic_base_image_paths": graphic_base_image_paths,
        # 向后兼容
        "cover_path": str(slide_paths[0]),
        "image_key": image_keys[0] if image_keys else "",
        "current_review_message_id": message_id,
        "note_id": note_id,
        "revision_count": 0,
        "topic_data_style": topic_data.get("style") if topic_data else None,
    }
    save_review_state(run_dir, state)

    result["status"] = "waiting_review"
    result["task_dir"] = str(run_dir)
    result["steps"]["review_card"] = message_id
    _save_result(run_dir, result)

    if auto_approve:
        print("  ⚠️  --auto-approve 已弃用，当前仅会停在初稿审核阶段。")

    print("\n" + "=" * 60)
    print("🎉 初稿已发出，流程已暂停等待审核")
    print(f"   任务目录: {run_dir}")
    print(f"   审核卡片: {message_id}")
    print(f"   图片数量: {len(slide_paths)} 张")
    print("=" * 60)

    return result


def resume_review_action(
    action: str,
    message_id: str,
    dry_run: bool = False,
    config_path: str | None = None,
    revision_notes: str | None = None,
    revision_scope: str | None = None,
) -> dict[str, Any]:
    """根据卡片动作继续执行：approve / refresh_* / modify / rewrite。"""

    try:
        run_dir, state = load_review_state(message_id)
    except FileNotFoundError as e:
        return _blocked_missing_review_state(action, message_id, e)
    current_message_id = state.get("current_review_message_id")
    if current_message_id != message_id:
        print(
            f"  ⚠️  该卡片已过期：当前卡片是 {current_message_id}，"
            f"收到的是 {message_id}"
        )
        result = {
            "status": "stale",
            "task_dir": str(run_dir),
            "steps": {
                "stale_review_card": message_id,
                "current_review_card": current_message_id,
            },
        }
        _save_result(run_dir, result)
        return result

    payload = state["payload"]
    topic = state["topic"]
    audience = state["audience"]
    skip_image = bool(state.get("skip_image", False))
    effective_dry_run = dry_run or bool(state.get("dry_run", False))
    note_id = state.get("note_id", run_dir.name)
    config = {} if effective_dry_run else load_config(config_path)
    result: dict[str, Any] = {"status": "running", "steps": {}, "task_dir": str(run_dir)}

    print("=" * 60)
    print("🚀 小红书 + 飞书审核回流")
    print(f"   主题：{topic}")
    print(f"   受众：{audience}")
    print(f"   动作：{action}")
    print(f"   模式：{'dry-run（本地测试）' if effective_dry_run else '真实运行'}")
    print("=" * 60)

    if action == "approve":
        print("\n✅ 审核通过，发送最终稿卡片...")
        full_content = format_full_content(payload)
        if effective_dry_run:
            final_message_id = f"msg_final_{run_dir.name}"
            print("  ⏭️  dry-run 模式，跳过发送")
            print(f"\n  ── 最终稿预览 ──")
            print(f"  标题: ✅ 最终稿：{payload['cover_title']}")
            print(f"  文案:\n{full_content}")
        else:
            feishu = FeishuClient(config)
            final_message_id = feishu.send_final_card(
                image_key=state["image_key"],
                title=payload["cover_title"],
                full_content=full_content,
                tags=" ".join(f"#{t}" for t in payload["hashtags"]),
            )
            print(f"  ✅ 最终稿卡片已发送: {final_message_id}")
            print("  🍠 点击卡片上的按钮即可跳转小红书发布！")

        state["status"] = "approved"
        state["final_message_id"] = final_message_id
        state["approved_at"] = timestamp()
        state["current_review_message_id"] = None
        state["pending_revision_mode"] = None
        save_review_state(run_dir, state)
        result["status"] = "ok"
        result["steps"]["action"] = "approve"
        result["steps"]["final_card"] = final_message_id
        _save_result(run_dir, result)

        print("\n" + "=" * 60)
        print("🎉 审核通过，已进入最终稿阶段")
        print(f"   任务目录: {run_dir}")
        print("=" * 60)
        return result

    if action in {"refresh_cover", "refresh_graphics"}:
        slide_paths = _normalized_slide_paths(run_dir, state)
        image_keys = _normalized_image_keys(state)
        state["review_action_mode"] = "image_refresh"
        state["last_action"] = action
        state["pending_revision_mode"] = None
        invalid_state = _validate_multi_image_review_state(
            run_dir,
            state,
            action,
            slide_paths,
            image_keys,
        )
        if invalid_state:
            return invalid_state
        prompt_templates = _persisted_image_templates(state)
        style_hint = _persisted_review_style_hint(state)
        cover_base_image_path = _normalize_optional_path(state.get("cover_base_image_path"))
        graphic_base_image_paths = _normalize_optional_paths(state.get("graphic_base_image_paths"))

        if action == "refresh_cover":
            refresh_index = int(state.get("cover_refresh_count", 0)) + 1
            try:
                if cover_base_image_path:
                    cover_path = _render_overlay_cover(
                        run_dir=run_dir,
                        payload=payload,
                        image_templates=prompt_templates,
                        base_image_path=cover_base_image_path,
                        refresh_index=refresh_index,
                        current_cover_path=state.get("cover_path"),
                    )
                elif prompt_templates:
                    cover_path = _render_prompt_cover(
                        run_dir=run_dir,
                        payload=payload,
                        config=config,
                        dry_run=effective_dry_run,
                        skip_image=skip_image,
                        image_templates=prompt_templates,
                        refresh_index=refresh_index,
                        current_cover_path=state.get("cover_path"),
                    )
                else:
                    cover_path = _render_refreshed_cover(
                        run_dir=run_dir,
                        payload=payload,
                        style_hint=style_hint,
                        config=config,
                        dry_run=effective_dry_run,
                        skip_image=skip_image,
                        refresh_index=refresh_index,
                        current_cover_path=state.get("cover_path"),
                    )
            except GeminiImageError as e:
                print(f"  ❌ 刷新封面图失败: {e}")
                result["status"] = "failed"
                result["error"] = f"刷新封面图失败: {e}"
                _save_result(run_dir, result)
                return result

            try:
                uploaded_keys = upload_slide_images([cover_path], config, effective_dry_run)
                image_key = uploaded_keys[0]
                if effective_dry_run:
                    print("  ⏭️  dry-run 模式，跳过上传")
                else:
                    print(f"  ✅ 新封面已上传: {image_key}")
            except Exception as e:
                print(f"  ❌ 刷新封面上传失败: {e}")
                result["status"] = "failed"
                result["error"] = f"刷新封面上传失败: {e}"
                _save_result(run_dir, result)
                return result

            updated_slide_paths = [str(cover_path), *slide_paths[1:]]
            updated_image_keys = [image_key, *image_keys[1:]]
            new_message_id = _send_review_card(
                payload=payload,
                image_keys=updated_image_keys,
                note_id=note_id,
                config=config,
                dry_run=effective_dry_run,
                message_suffix=f"refresh_cover_{run_dir.name}_{refresh_index}",
            )

            state["status"] = "waiting_review"
            state["slide_paths"] = updated_slide_paths
            state["image_keys"] = updated_image_keys
            state["cover_path"] = str(cover_path)
            state["image_key"] = image_key
            state["current_review_message_id"] = new_message_id
            state["cover_refresh_count"] = refresh_index
            save_review_state(run_dir, state)

            result["status"] = "waiting_review"
            result["steps"]["action"] = action
            result["steps"]["review_card"] = new_message_id
            _save_result(run_dir, result)

            print("\n" + "=" * 60)
            print("🎉 已完成图片刷新，等待下一轮审核")
            print(f"   任务目录: {run_dir}")
            print(f"   新审核卡片: {new_message_id}")
            print("=" * 60)
            return result

        graphic_slot_count = max(len(slide_paths), len(image_keys)) - 1
        if graphic_slot_count <= 0:
            return _blocked_image_refresh(
                run_dir,
                state,
                action,
                reason="no_distinct_graphics_lane",
                message="当前任务没有独立内容配图可刷新，仅有单张封面图。",
            )
        if not style_hint and not prompt_templates:
            return _blocked_image_refresh(
                run_dir,
                state,
                action,
                reason="missing_graphics_style_metadata",
                message="当前任务缺少持久化的多图样式元数据，无法安全刷新内容配图。",
            )

        refresh_index = int(state.get("graphics_refresh_count", 0)) + 1
        current_graphic_paths = slide_paths[1 : 1 + graphic_slot_count]
        if len(current_graphic_paths) != graphic_slot_count:
            return _blocked_image_refresh(
                run_dir,
                state,
                action,
                reason="graphics_refresh_unsupported",
                message="当前任务的内容配图轨道不完整，无法安全地只刷新内容配图。",
            )
        try:
            if graphic_base_image_paths:
                refreshed_graphics = _render_overlay_graphics(
                    run_dir=run_dir,
                    payload=payload,
                    image_templates=prompt_templates,
                    graphic_base_image_paths=graphic_base_image_paths,
                    refresh_index=refresh_index,
                    current_graphic_paths=current_graphic_paths,
                )
                if len(refreshed_graphics) < graphic_slot_count:
                    fallback_graphics = _render_prompt_graphics(
                        run_dir=run_dir,
                        payload=payload,
                        config=config,
                        dry_run=effective_dry_run,
                        skip_image=skip_image,
                        image_templates=prompt_templates,
                        refresh_index=refresh_index,
                        current_graphic_paths=current_graphic_paths,
                    )
                    refreshed_graphics.extend(fallback_graphics[len(refreshed_graphics):graphic_slot_count])
            elif prompt_templates:
                refreshed_graphics = _render_prompt_graphics(
                    run_dir=run_dir,
                    payload=payload,
                    config=config,
                    dry_run=effective_dry_run,
                    skip_image=skip_image,
                    image_templates=prompt_templates,
                    refresh_index=refresh_index,
                    current_graphic_paths=current_graphic_paths,
                )
            else:
                refreshed_graphics = _render_refreshed_graphics(
                    run_dir=run_dir,
                    payload=payload,
                    style_hint=style_hint,
                    refresh_index=refresh_index,
                    current_graphic_paths=current_graphic_paths,
                )
        except Exception as e:
            print(f"  ❌ 刷新内容配图失败: {e}")
            result["status"] = "failed"
            result["error"] = f"刷新内容配图失败: {e}"
            _save_result(run_dir, result)
            return result

        try:
            new_graphic_keys = upload_slide_images(refreshed_graphics, config, effective_dry_run)
            if effective_dry_run:
                print("  ⏭️  dry-run 模式，跳过上传")
            else:
                print(f"  ✅ 新内容配图已上传: {len(new_graphic_keys)} 张")
        except Exception as e:
            print(f"  ❌ 刷新内容配图上传失败: {e}")
            result["status"] = "failed"
            result["error"] = f"刷新内容配图上传失败: {e}"
            _save_result(run_dir, result)
            return result

        cover_key = image_keys[0] if image_keys else str(state.get("image_key") or "")
        if not cover_key:
            return _blocked_image_refresh(
                run_dir,
                state,
                action,
                reason="missing_cover_asset",
                message="当前任务缺少封面图上传记录，无法在不重跑全文案的前提下刷新内容配图。",
            )

        updated_slide_paths = [slide_paths[0], *[str(path) for path in refreshed_graphics]]
        updated_image_keys = [cover_key, *new_graphic_keys]
        new_message_id = _send_review_card(
            payload=payload,
            image_keys=updated_image_keys,
            note_id=note_id,
            config=config,
            dry_run=effective_dry_run,
            message_suffix=f"refresh_graphics_{run_dir.name}_{refresh_index}",
        )

        state["status"] = "waiting_review"
        state["slide_paths"] = updated_slide_paths
        state["image_keys"] = updated_image_keys
        state["cover_path"] = slide_paths[0]
        state["image_key"] = cover_key
        state["current_review_message_id"] = new_message_id
        state["graphics_refresh_count"] = refresh_index
        save_review_state(run_dir, state)

        result["status"] = "waiting_review"
        result["steps"]["action"] = action
        result["steps"]["review_card"] = new_message_id
        _save_result(run_dir, result)

        print("\n" + "=" * 60)
        print("🎉 已完成图片刷新，等待下一轮审核")
        print(f"   任务目录: {run_dir}")
        print(f"   新审核卡片: {new_message_id}")
        print("=" * 60)
        return result

    if action not in {"modify", "rewrite"}:
        raise ValueError(f"不支持的动作: {action}")

    if revision_notes:
        print(f"\n✏️  收到 {action}，将按修改说明重新生成初稿...")
    else:
        print(f"\n✏️  收到 {action}，开始重新生成初稿...")
    try:
        new_payload = generate_xhs_payload(
            topic,
            audience,
            config,
            dry_run=effective_dry_run,
            revision_mode=action,
            revision_notes=revision_notes,
            revision_scope=revision_scope,
            existing_payload=payload,
        )
    except Exception as e:
        print(f"  ❌ 重新生成素材包失败: {e}")
        result["status"] = "failed"
        result["error"] = f"重新生成素材包失败: {e}"
        _save_result(run_dir, result)
        return result
    save_json_file(run_dir / "payload.json", new_payload)
    save_text_file(run_dir / "cover_title.txt", new_payload["cover_title"] + "\n")
    save_text_file(run_dir / "cover_prompt.txt", new_payload["cover_prompt"] + "\n")
    for i, v in enumerate(new_payload["variants"], 1):
        save_text_file(
            run_dir / f"variant_{i}.md",
            f"# {v['title']}\n\n**角度：** {v['angle']}\n\n{v['body']}\n",
        )

    current_slide_paths = _normalized_slide_paths(run_dir, state)
    style_hint = _persisted_review_style_hint(state)
    prompt_templates = _persisted_image_templates(state)
    current_image_keys = _normalized_image_keys(state)
    cover_base_image_path = _normalize_optional_path(state.get("cover_base_image_path"))
    graphic_base_image_paths = _normalize_optional_paths(state.get("graphic_base_image_paths"))
    regenerated_slide_paths: list[Path] | None = None
    regenerated_image_keys: list[str] | None = None

    if max(len(current_slide_paths), len(current_image_keys)) > 1 and not prompt_templates:
        print("  ⚠️  当前旧版多图审核状态缺少模板元数据，无法安全继续修改/重写。")
        state["last_action"] = action
        state["pending_revision_mode"] = None
        result["status"] = "blocked"
        result["reason"] = "missing_image_templates_metadata"
        result["message"] = "当前旧版多图审核状态缺少模板元数据，无法安全继续修改/重写。"
        result["steps"]["action"] = action
        result["steps"]["reason"] = "missing_image_templates_metadata"
        save_review_state(run_dir, state)
        _save_result(run_dir, result)
        return result

    if prompt_templates:
        revision_index = int(state.get("revision_count", 0)) + 1
        try:
            regenerated_slide_paths = _render_mixed_slide_set(
                run_dir=run_dir,
                payload=new_payload,
                config=config,
                dry_run=effective_dry_run,
                skip_image=skip_image,
                image_templates=prompt_templates,
                cover_base_image_path=cover_base_image_path,
                graphic_base_image_paths=graphic_base_image_paths,
                marker="rev",
                version_index=revision_index,
                current_slide_paths=current_slide_paths,
            )
        except Exception as e:
            print(f"  ❌ 重新生成多图审核素材失败: {e}")
            result["status"] = "failed"
            result["error"] = f"重新生成多图审核素材失败: {e}"
            _save_result(run_dir, result)
            return result
        try:
            regenerated_image_keys = upload_slide_images(regenerated_slide_paths, config, effective_dry_run)
            if effective_dry_run:
                print("  ⏭️  dry-run 模式，跳过上传")
            else:
                print(f"  ✅ 新审核图片已上传: {len(regenerated_image_keys)} 张")
        except Exception as e:
            print(f"  ❌ 重新上传多图审核素材失败: {e}")
            result["status"] = "failed"
            result["error"] = f"重新上传多图审核素材失败: {e}"
            _save_result(run_dir, result)
            return result
        cover_path = regenerated_slide_paths[0]
        image_key = regenerated_image_keys[0]
    elif style_hint:
        try:
            cover_path = generate_cover_art(run_dir, new_payload, config, effective_dry_run, skip_image)
        except GeminiImageError as e:
            print(f"  ❌ 重新生成封面图失败: {e}")
            result["status"] = "failed"
            result["error"] = f"重新生成封面图失败: {e}"
            _save_result(run_dir, result)
            return result
        try:
            image_key = upload_cover_image(cover_path, config, effective_dry_run)
            if effective_dry_run:
                print("  ⏭️  dry-run 模式，跳过上传")
            else:
                print(f"  ✅ 新封面已上传: {image_key}")
        except Exception as e:
            print(f"  ❌ 重新上传失败: {e}")
            result["status"] = "failed"
            result["error"] = f"重新上传失败: {e}"
            _save_result(run_dir, result)
            return result
    else:
        try:
            cover_path = generate_cover_art(run_dir, new_payload, config, effective_dry_run, skip_image)
        except GeminiImageError as e:
            print(f"  ❌ 重新生成封面图失败: {e}")
            result["status"] = "failed"
            result["error"] = f"重新生成封面图失败: {e}"
            _save_result(run_dir, result)
            return result
        try:
            image_key = upload_cover_image(cover_path, config, effective_dry_run)
            if effective_dry_run:
                print("  ⏭️  dry-run 模式，跳过上传")
            else:
                print(f"  ✅ 新封面已上传: {image_key}")
        except Exception as e:
            print(f"  ❌ 重新上传失败: {e}")
            result["status"] = "failed"
            result["error"] = f"重新上传失败: {e}"
            _save_result(run_dir, result)
            return result

    card_content = format_card_content(new_payload, 0)
    tags_str = " ".join(f"#{t}" for t in new_payload["hashtags"][:6])
    if effective_dry_run:
        new_message_id = f"msg_{action}_{run_dir.name}_rev{int(state.get('revision_count', 0)) + 1}"
        print(f"  ⏭️  dry-run 模式，跳过发送新审核卡")
        print(f"  新卡片内容:\n{card_content}")
    else:
        feishu = FeishuClient(config)
        new_message_id = feishu.send_review_card(
            image_key=regenerated_image_keys if regenerated_image_keys else image_key,
            title=f"🎨 小红书笔记审核 — {new_payload['cover_title']}",
            content=card_content,
            tags=tags_str,
            note_id=note_id,
        )
        print(f"  ✅ 新审核卡片已发送: {new_message_id}")
        print("  ⏸️  已停在新初稿阶段，等你继续点通过或刷新图片。")

    state["status"] = "waiting_review"
    state["payload"] = new_payload
    if regenerated_slide_paths and regenerated_image_keys:
        state["slide_paths"] = [str(path) for path in regenerated_slide_paths]
        state["image_keys"] = list(regenerated_image_keys)
    else:
        state["slide_paths"] = [str(cover_path)]
        state["image_keys"] = [image_key]
    state["cover_path"] = str(cover_path)
    state["image_key"] = image_key
    state["current_review_message_id"] = new_message_id
    state["revision_count"] = int(state.get("revision_count", 0)) + 1
    state["review_action_mode"] = "revision"
    state["last_action"] = action
    state["pending_revision_mode"] = None
    if revision_notes:
        state["last_revision_notes"] = revision_notes
    if revision_scope:
        state["last_revision_scope"] = revision_scope
    save_review_state(run_dir, state)

    result["status"] = "waiting_review"
    result["steps"]["action"] = action
    result["steps"]["review_card"] = new_message_id
    _save_result(run_dir, result)

    print("\n" + "=" * 60)
    print("🎉 已完成重新生成，等待下一轮审核")
    print(f"   任务目录: {run_dir}")
    print(f"   新审核卡片: {new_message_id}")
    print("=" * 60)

    return result


def _save_result(run_dir: Path, result: dict) -> None:
    save_json_file(run_dir / "result.json", result)


# ── CLI 入口 ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="小红书 + 飞书端到端自动化流程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 本地测试（dry-run，不调真实 API）
  python scripts/xhs_feishu_flow.py --topic "AI 自动化提效" --dry-run --mode draft

  # 真实运行（先发初稿审核卡）
  python scripts/xhs_feishu_flow.py --topic "教培机构 AI 内容运营" --audience "校长" --mode draft

  # 审核卡按钮回流（由 Feishu card.action.trigger 触发）
  python scripts/xhs_feishu_flow.py --topic "测试" --mode resume --action approve --message-id om_xxx

  # 修改按钮回流（先打开修改说明卡）
  python scripts/xhs_feishu_flow.py --mode request-edit --action modify --message-id om_xxx
        """,
    )
    parser.add_argument("--topic", default=None, help="小红书笔记主题（draft 模式必填；resume 模式可省略）")
    parser.add_argument("--audience", default="教育行业运营负责人", help="目标人群")
    parser.add_argument("--dry-run", action="store_true", help="本地测试模式")
    parser.add_argument("--skip-image", action="store_true", help="跳过真实生图，改用占位图")
    parser.add_argument("--base-image", default=None, help="客户提供的封面底图路径")
    parser.add_argument("--graphic-base-image", action="append", default=None, help="客户提供的正文配图底图路径，可传多次")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")
    parser.add_argument(
        "--mode",
        choices=["draft", "resume", "request-edit"],
        default="draft",
        help="draft=先发初稿审核卡；resume=根据卡片动作继续；request-edit=打开修改说明卡",
    )
    parser.add_argument(
        "--action",
        choices=["approve", "refresh_cover", "refresh_graphics", "modify", "rewrite"],
        default=None,
        help="resume 模式下的卡片动作",
    )
    parser.add_argument(
        "--message-id",
        default=None,
        help="resume 模式下的审核卡消息 ID",
    )
    parser.add_argument(
        "--revision-notes",
        default=None,
        help="resume 模式下的修改说明",
    )
    parser.add_argument(
        "--revision-notes-file",
        default=None,
        help="resume 模式下的修改说明文件（json/yaml/txt）",
    )
    parser.add_argument(
        "--revision-scope",
        default=None,
        help="resume 模式下的修改范围",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="已弃用，保留向后兼容，不再自动通过",
    )
    parser.add_argument("--config", default=None, help="配置文件路径")
    args = parser.parse_args()

    if args.mode == "resume":
        if not args.action:
            raise SystemExit("--mode resume 时必须同时提供 --action")
        if not args.message_id:
            raise SystemExit("--mode resume 时必须同时提供 --message-id")
        revision_notes = args.revision_notes
        revision_scope = args.revision_scope
        if args.revision_notes_file:
            file_notes, file_scope = load_revision_notes_from_file(args.revision_notes_file)
            revision_notes = revision_notes or file_notes
            revision_scope = revision_scope or file_scope
        result = resume_review_action(
            action=args.action,
            message_id=args.message_id,
            dry_run=args.dry_run,
            config_path=args.config,
            revision_notes=revision_notes,
            revision_scope=revision_scope,
        )
        if args.json:
            print("__JSON_RESULT__")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.mode == "request-edit":
        if not args.action:
            raise SystemExit("--mode request-edit 时必须同时提供 --action")
        if not args.message_id:
            raise SystemExit("--mode request-edit 时必须同时提供 --message-id")
        if args.action not in {"modify", "rewrite"}:
            raise SystemExit("--mode request-edit 仅支持 modify/rewrite，不接受 refresh_* 动作")
        result = request_revision_notes(
            action=args.action,
            message_id=args.message_id,
            dry_run=args.dry_run,
            config_path=args.config,
        )
        if args.json:
            print("__JSON_RESULT__")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if not args.topic:
        raise SystemExit("--mode draft 时必须提供 --topic")

    result = run_flow(
        topic=args.topic,
        audience=args.audience,
        dry_run=args.dry_run,
        skip_image=args.skip_image,
        auto_approve=args.auto_approve,
        config_path=args.config,
        base_image_path=args.base_image,
        graphic_base_image_paths=args.graphic_base_image,
    )
    if args.json:
        print("__JSON_RESULT__")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
