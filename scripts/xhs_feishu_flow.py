#!/usr/bin/env python3
"""小红书 + 飞书端到端流程脚本。

完整流程：
  1. 生成小红书素材包（文案 + 标签 + 封面 prompt）
  2. 生成封面图（Gemini 网页自动化或占位图）
  3. 上传图片到飞书
  4. 发送审核卡片到飞书（✅通过 / ✏️修改 / ❌重写）
  5. 等待飞书 card.action.trigger 回流
  6. 通过 → 发送最终稿卡片；修改/重写 → 先打开修改说明卡，填写后再重新生成审核卡

用法：
  python scripts/xhs_feishu_flow.py --topic "主题" --audience "目标人群"
  python scripts/xhs_feishu_flow.py --topic "主题" --dry-run   # 占位图+跳过飞书
"""

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

from common import OUTPUT_DIR, ensure_dir, load_config, make_run_dir, save_json_file, save_text_file, timestamp
from feishu_client import FeishuClient
from gemini_image import generate_image, _generate_placeholder, GeminiImageError
from xhs_topic_generator import get_topic_by_title, get_topics_by_subject, WUHAN_TOPICS
from xhs_image_renderer import render_topic_images, render_image


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
) -> dict[str, Any]:
    """生成小红书素材包。

    dry_run 时使用 stub 数据；revision_mode 用于修改/重写回路。
    """
    if not dry_run:
        try:
            from llm_client import OpenAICompatibleLLM, LLMConfigError
            client = OpenAICompatibleLLM(config)
            client.require_ready()
            system = (
                "你是一名擅长教育行业内容增长的小红书策划。"
                "请输出严格 JSON，字段必须包含：positioning, cover_title, cover_prompt, hashtags, publish_checklist, variants。"
                "variants 必须有 3 条，每条包含 title, body, angle。"
            )
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
        except Exception as e:
            print(f"  ⚠️  LLM 调用失败 ({e})，回退到 stub 数据")

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


def generate_slide_images(
    run_dir: Path,
    payload: dict[str, Any],
    topic_data: dict[str, Any] | None,
    config: dict[str, Any],
    dry_run: bool,
    skip_image: bool,
) -> list[Path]:
    """生成多张幻灯片图片（使用 HTML 渲染引擎）。

    如果匹配到预设选题（topic_data），使用 HTML 模板渲染；
    否则回退到 AI 生图（单张封面）。
    """
    if topic_data:
        # 使用 HTML 渲染引擎
        print(f"  🧠 渲染引擎: HTML模板 (style={topic_data.get('style', 'info_card')})")
        try:
            images = render_topic_images(topic_data, run_dir / "slides", count=3)
            print(f"  ✅ {len(images)} 张幻灯片已生成")
            return images
        except Exception as e:
            print(f"  ⚠️  HTML 渲染失败 ({e})，回退到 AI 生图")

    # 回退：传统 AI 生图（单张封面）
    cover_path = run_dir / "cover.png"
    backend = config.get("gemini_image", {}).get("backend", "gemini_cli") if config else "gemini_cli"
    print(f"  🧠 封面后端: {backend}")
    if skip_image or dry_run:
        _generate_placeholder(cover_path, payload.get("cover_prompt", ""))
        print(f"  ✅ 占位图已生成: {cover_path}")
    else:
        cover_path = generate_image(
            payload["cover_prompt"],
            cover_path,
            config,
            allow_placeholder=False,
        )
        print(f"  ✅ 封面图已生成: {cover_path}")
    return [cover_path]


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
    run_dir, state = load_review_state(message_id)
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


def run_flow(
    topic: str,
    audience: str,
    dry_run: bool = False,
    skip_image: bool = False,
    auto_approve: bool = False,
    config_path: str | None = None,
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

    # ── Step 0: 匹配预设选题 ────────────────────────────────
    topic_data = _match_topic_data(topic)

    # ── Step 1: 生成素材包 ──────────────────────────────────
    print("\n📦 步骤 1/4：生成小红书素材包...")
    # 如果匹配到预设选题，用选题里的标签和标题
    if topic_data:
        payload = generate_xhs_payload(topic, audience, config, dry_run)
        payload["hashtags"] = topic_data.get("tags", payload["hashtags"])
        payload["cover_title"] = topic_data.get("title", payload["cover_title"])
    else:
        payload = generate_xhs_payload(topic, audience, config, dry_run)

    run_dir = make_run_dir("xhs_feishu", topic)
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
            run_dir, payload, topic_data, config, dry_run, skip_image
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
            print("  ⏸️  已暂停在初稿审核阶段，等你点通过/修改/重写后再继续。")
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
    """根据卡片动作继续执行：approve / modify / rewrite。"""

    run_dir, state = load_review_state(message_id)
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

    if action not in {"modify", "rewrite"}:
        raise ValueError(f"不支持的动作: {action}")

    if revision_notes:
        print(f"\n✏️  收到 {action}，将按修改说明重新生成初稿...")
    else:
        print(f"\n✏️  收到 {action}，开始重新生成初稿...")
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
    save_json_file(run_dir / "payload.json", new_payload)
    save_text_file(run_dir / "cover_title.txt", new_payload["cover_title"] + "\n")
    save_text_file(run_dir / "cover_prompt.txt", new_payload["cover_prompt"] + "\n")
    for i, v in enumerate(new_payload["variants"], 1):
        save_text_file(
            run_dir / f"variant_{i}.md",
            f"# {v['title']}\n\n**角度：** {v['angle']}\n\n{v['body']}\n",
        )

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
            image_key=image_key,
            title=f"🎨 小红书笔记审核 — {new_payload['cover_title']}",
            content=card_content,
            tags=tags_str,
            note_id=note_id,
        )
        print(f"  ✅ 新审核卡片已发送: {new_message_id}")
        print("  ⏸️  已停在新初稿阶段，等你继续点通过/修改/重写。")

    state["status"] = "waiting_review"
    state["payload"] = new_payload
    state["cover_path"] = str(cover_path)
    state["image_key"] = image_key
    state["current_review_message_id"] = new_message_id
    state["revision_count"] = int(state.get("revision_count", 0)) + 1
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
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")
    parser.add_argument(
        "--mode",
        choices=["draft", "resume", "request-edit"],
        default="draft",
        help="draft=先发初稿审核卡；resume=根据卡片动作继续；request-edit=打开修改说明卡",
    )
    parser.add_argument(
        "--action",
        choices=["approve", "modify", "rewrite"],
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
    )
    if args.json:
        print("__JSON_RESULT__")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
