#!/usr/bin/env python3
"""公众号两阶段内容生成与草稿箱推送脚本。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import (
    OUTPUT_DIR,
    config_state,
    ensure_dir,
    load_config,
    load_yaml_file,
    make_run_dir,
    save_json_file,
    save_text_file,
    save_yaml_file,
)
from gen_image import image_backend_ready, render_image_to_path
from gen_image_prompts import (
    extract_title,
    generate_cover_prompt,
    generate_illustration_prompt,
    load_cover_style,
    load_image_style,
    extract_image_slots,
)
from llm_client import LLMConfigError, OpenAICompatibleLLM
from md_to_html import md_to_html
from wx_api import add_draft, upload_image_for_article, upload_thumb_image


def load_writing_style(style_name: str) -> dict[str, Any]:
    style_dir = OUTPUT_DIR.parent / "styles" / "writing"
    direct = style_dir / f"{style_name}.yaml"
    preset = style_dir / "_presets" / f"{style_name}.yaml"
    target = direct if direct.exists() else preset
    if not target.exists():
        raise FileNotFoundError(f"找不到文风配置: {style_name}")
    return load_yaml_file(target)


def llm_or_stub(config: dict[str, Any], dry_run: bool) -> OpenAICompatibleLLM | None:
    client = OpenAICompatibleLLM(config)
    if dry_run:
        return None
    client.require_ready()
    return client


def outline_stub(topic: str, audience: str, style_name: str) -> dict[str, Any]:
    return {
        "title": f"{topic}：教育团队怎么把重复内容工作交给 AI",
        "audience_summary": audience,
        "style_recommendation": {
            "writing_style": style_name,
            "cover_style": "ai_play",
            "image_style": "ai_play",
            "layout_style": "blue_dot",
            "reason": "首期验证优先选择最稳妥的现有组合，方便后续 prompt 调优和回归。",
        },
        "digest": "从选题、大纲、成文到配图和草稿箱推送，梳理教育自媒体首期自动化落地路径。",
        "outline": [
            {
                "title": "为什么教育团队需要先做辅助式自动化",
                "key_points": ["内容岗位重复劳动高", "平台风控要求保留人工审核"],
                "suggested_image": "团队梳理内容流程、人工审核节点清晰可见",
            },
            {
                "title": "公众号首期最值得先打通哪几步",
                "key_points": ["选题和大纲", "文章成文", "配图和草稿箱"],
                "suggested_image": "公众号内容生产流水线示意图",
            },
            {
                "title": "小红书为什么先做素材包而不是自动发帖",
                "key_points": ["平台敏感动作风控高", "素材包更适合人工复核"],
                "suggested_image": "小红书封面、文案、标签素材平铺展示",
            },
            {
                "title": "项目如何分阶段验收和继续扩展",
                "key_points": ["先跑通", "再联调", "最后扩模块"],
                "suggested_image": "阶段里程碑看板",
            },
        ],
    }


def build_outline_prompts(
    topic: str,
    audience: str,
    config: dict[str, Any],
    writing_style: dict[str, Any],
) -> tuple[str, str]:
    system_prompt = (
        "你是教育行业自媒体自动化顾问。"
        "请为公众号任务输出严格 JSON，字段必须包含："
        "title, audience_summary, style_recommendation, digest, outline。"
        "outline 必须是 4-6 个章节的数组，每项包含 title, key_points, suggested_image。"
    )
    user_prompt = (
        f"主题：{topic}\n"
        f"目标读者：{audience}\n"
        f"默认文风：{config['defaults'].get('writing_style', 'tech_blogger')}\n"
        f"文风画像：{json.dumps(writing_style, ensure_ascii=False)}\n"
        "要求：\n"
        "1. 给出最适合首期交付验证的风格组合。\n"
        "2. 大纲采用 4-6 个 ## 大章节。\n"
        "3. 每章给出 2-3 个关键点。\n"
        "4. 摘要控制在 120 字内。\n"
        "5. 不要写正文，只返回 JSON。"
    )
    return system_prompt, user_prompt


def render_outline_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"# {data['title']}",
        "",
        f"**目标读者**：{data['audience_summary']}",
        f"**摘要**：{data['digest']}",
        "",
        "## 推荐风格组合",
        "",
        f"- 文风：`{data['style_recommendation']['writing_style']}`",
        f"- 头图：`{data['style_recommendation']['cover_style']}`",
        f"- 插图：`{data['style_recommendation']['image_style']}`",
        f"- 排版：`{data['style_recommendation']['layout_style']}`",
        f"- 原因：{data['style_recommendation']['reason']}",
        "",
        "## 大纲",
        "",
    ]
    for index, item in enumerate(data["outline"], start=1):
        lines.append(f"### {index}. {item['title']}")
        for point in item["key_points"]:
            lines.append(f"- {point}")
        lines.append(f"- 配图建议：{item['suggested_image']}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def article_stub(outline_data: dict[str, Any], writing_style: dict[str, Any]) -> str:
    title = outline_data["title"]
    lines = [
        f"# {title}",
        "",
        "开头这部分先把问题摆清楚：教育行业做内容，不是不会写，而是持续稳定地写太耗人。",
        "![封面图：教育自媒体团队和 AI 协作](placeholder)",
        "",
    ]
    for idx, section in enumerate(outline_data["outline"], start=1):
        lines.append(f"## {section['title']}")
        lines.append(
            f"从 {writing_style['name']} 的口吻来看，这一节最重要的不是讲概念，而是把真实执行路径讲明白。"
        )
        for point in section["key_points"]:
            lines.append(f"### 关键点：{point}")
            lines.append(
                f"围绕“{point}”，团队可以先做小范围验证，再把稳定动作沉淀成固定流程。"
            )
        if idx < len(outline_data["outline"]):
            lines.append(f"![插图：{section['suggested_image']}](placeholder)")
        lines.append("")
    lines.append("## 收尾建议")
    lines.append("先把第一阶段跑通，拿到真实产出和反馈，再扩到私域回复和视频模块。")
    return "\n".join(lines).strip() + "\n"


def build_article_prompts(
    outline_data: dict[str, Any],
    audience: str,
    writing_style: dict[str, Any],
    article_config: dict[str, Any],
) -> tuple[str, str]:
    system_prompt = (
        "你是一名教育行业公众号作者。请写出完整 Markdown 文章。"
        "必须遵守："
        "1. 一级标题只有一个；"
        "2. 大章节用 ##，子标题用 ###；"
        "3. 必须插入图片占位符，格式为 ![描述](placeholder)；"
        "4. 不要输出 JSON；"
        "5. 语气要符合提供的文风设定。"
    )
    user_prompt = (
        f"文章标题：{outline_data['title']}\n"
        f"目标读者：{audience}\n"
        f"建议字数：{article_config.get('default_length', 5000)}\n"
        f"文风设定：{json.dumps(writing_style, ensure_ascii=False)}\n"
        f"大纲：{json.dumps(outline_data['outline'], ensure_ascii=False)}\n"
        "要求：\n"
        "1. 第一段后插入一张封面图占位。\n"
        "2. 至少再插入两张正文插图占位。\n"
        "3. 内容突出‘AI 辅助 + 人工审核’的稳妥模式。\n"
        "4. 结尾给出可执行建议。\n"
    )
    return system_prompt, user_prompt


def render_prompt_manifest(
    article_text: str,
    config: dict[str, Any],
    output_path: Path,
    title: str,
) -> list[dict[str, Any]]:
    slots = extract_image_slots(article_text)
    image_style = load_image_style(config["defaults"].get("image_style"))
    cover_style = load_cover_style(config["defaults"].get("cover_style"))
    prompts: list[dict[str, Any]] = []
    for index, slot in enumerate(slots):
        is_cover = index == 0
        if is_cover:
            prompt, negative, size_cfg = generate_cover_prompt(slot, cover_style, title)
            img_type = "cover"
            filename = "cover.png"
        else:
            prompt, negative, size_cfg = generate_illustration_prompt(slot, image_style)
            img_type = "illustration"
            filename = f"ill_{index}.png"
        prompts.append(
            {
                "index": index,
                "type": img_type,
                "width": size_cfg["width"],
                "height": size_cfg["height"],
                "size": f"{size_cfg['width']}x{size_cfg['height']}",
                "filename": filename,
                "prompt": prompt,
                "negative": negative,
                "context": slot["alt"] or "(context)",
            }
        )
    save_yaml_file(output_path, prompts)
    return prompts


def create_placeholder_png(path: Path, width: int, height: int, label: str) -> None:
    image = Image.new("RGB", (width, height), color=(236, 242, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((24, 24, width - 24, height - 24), outline=(71, 109, 197), width=4)
    draw.text((40, 40), label[:48], fill=(44, 62, 120))
    image.save(path)


def generate_assets(
    prompts: list[dict[str, Any]],
    run_dir: Path,
    config: dict[str, Any],
    *,
    dry_run: bool,
) -> list[Path]:
    generated = []
    for item in prompts:
        target = run_dir / item["filename"]
        if dry_run or not image_backend_ready(config):
            create_placeholder_png(target, item["width"], item["height"], item["context"])
        else:
            render_image_to_path(
                item["prompt"],
                str(target),
                (item["width"], item["height"]),
                config=config,
            )
        generated.append(target)
    return generated


def publish_or_stub(
    article_html: str,
    article_title: str,
    digest: str,
    author: str,
    run_dir: Path,
    image_files: list[Path],
    *,
    dry_run: bool,
    publish_draft: bool,
) -> dict[str, Any]:
    article_html_path = run_dir / "article.html"
    save_text_file(article_html_path, article_html)
    result: dict[str, Any] = {
        "status": "skipped",
        "reason": "publish-draft disabled",
        "article_html": str(article_html_path),
    }

    if not publish_draft:
        save_json_file(run_dir / "draft_push_result.json", result)
        return result

    if dry_run:
        fake_map = {path.name: str(path) for path in image_files}
        save_yaml_file(run_dir / "image_map.yaml", fake_map)
        result = {
            "status": "dry-run",
            "reason": "dry-run 模式未调用微信接口",
            "article_html": str(article_html_path),
            "image_map": str(run_dir / "image_map.yaml"),
        }
        save_json_file(run_dir / "draft_push_result.json", result)
        return result

    cover = next(path for path in image_files if path.name == "cover.png")
    image_map = {}
    for path in image_files:
        if path.name == "cover.png":
            continue
        image_map[path.name] = upload_image_for_article(str(path))
    save_yaml_file(run_dir / "image_map.yaml", image_map)

    image_map_for_html = {key: value for key, value in image_map.items()}
    html_with_urls = md_to_html(
        (run_dir / "article.md").read_text(encoding="utf-8"),
        None,
        image_map_for_html,
    )
    save_text_file(article_html_path, html_with_urls)

    thumb_media_id = upload_thumb_image(str(cover))
    draft_result = add_draft(
        title=article_title,
        content=html_with_urls,
        thumb_media_id=thumb_media_id,
        author=author,
        digest=digest,
    )
    result = {
        "status": "pushed",
        "media_id": draft_result["media_id"],
        "article_html": str(article_html_path),
        "image_map": str(run_dir / "image_map.yaml"),
    }
    save_json_file(run_dir / "draft_push_result.json", result)
    return result


def run_prepare(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    style_name = args.writing_style or config["defaults"].get("writing_style", "tech_blogger")
    writing_style = load_writing_style(style_name)
    run_dir = make_run_dir("wechat", args.topic)

    client = llm_or_stub(config, args.dry_run)
    if client is None:
        outline_data = outline_stub(args.topic, args.audience, style_name)
    else:
        system_prompt, user_prompt = build_outline_prompts(
            args.topic, args.audience, config, writing_style
        )
        outline_data = client.chat_json(system_prompt, user_prompt, temperature=0.4)

    outline_data.setdefault("style_recommendation", {})
    outline_data["style_recommendation"].setdefault("writing_style", style_name)
    outline_data["style_recommendation"].setdefault(
        "cover_style", config["defaults"].get("cover_style", "ai_play")
    )
    outline_data["style_recommendation"].setdefault(
        "image_style", config["defaults"].get("image_style", "ai_play")
    )
    outline_data["style_recommendation"].setdefault(
        "layout_style", config["defaults"].get("layout_style", "blue_dot")
    )
    outline_data["style_recommendation"].setdefault(
        "reason", "沿用现有稳定风格组合，便于首期联调。"
    )

    task = {
        "topic": args.topic,
        "audience": args.audience,
        "status": "outline_ready",
        "dry_run": args.dry_run,
        "outline_approved": False,
        "outline": outline_data,
    }
    save_json_file(run_dir / "task.json", task)
    save_text_file(run_dir / "outline.md", render_outline_markdown(outline_data))
    return {
        "status": "outline_ready",
        "task_dir": str(run_dir),
        "task_file": str(run_dir / "task.json"),
        "outline_file": str(run_dir / "outline.md"),
    }


def run_produce(args: argparse.Namespace) -> dict[str, Any]:
    task_dir = Path(args.task_dir).resolve()
    task = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    config = load_config(args.config)
    outline_data = task["outline"]
    style_name = outline_data["style_recommendation"]["writing_style"]
    writing_style = load_writing_style(style_name)
    publish_draft = args.publish_draft

    if not args.outline_approved:
        raise RuntimeError("produce 阶段必须显式传入 --outline-approved。")

    client = llm_or_stub(config, args.dry_run or task.get("dry_run", False))
    if client is None:
        article_text = article_stub(outline_data, writing_style)
    else:
        system_prompt, user_prompt = build_article_prompts(
            outline_data,
            task["audience"],
            writing_style,
            config.get("article", {}),
        )
        article_text = client.chat(system_prompt, user_prompt, max_tokens=6000)

    article_path = task_dir / "article.md"
    save_text_file(article_path, article_text)

    prompt_path = task_dir / "image_prompts.yaml"
    prompts = render_prompt_manifest(
        article_text,
        config,
        prompt_path,
        extract_title(article_text) or outline_data["title"],
    )
    image_files = generate_assets(
        prompts,
        task_dir,
        config,
        dry_run=args.dry_run or task.get("dry_run", False),
    )

    html = md_to_html(article_text, outline_data["style_recommendation"]["layout_style"], {})
    publish_result = publish_or_stub(
        html,
        outline_data["title"],
        outline_data.get("digest", ""),
        config.get("article", {}).get(
            "author",
            config.get("project", {}).get("default_author", "AI 内容实验室"),
        ),
        task_dir,
        image_files,
        dry_run=args.dry_run or task.get("dry_run", False),
        publish_draft=publish_draft,
    )

    task["status"] = "produced"
    task["outline_approved"] = True
    save_json_file(task_dir / "task.json", task)
    summary = {
        "status": "produced",
        "task_dir": str(task_dir),
        "article_file": str(article_path),
        "image_prompts": str(prompt_path),
        "article_html": str(task_dir / "article.html"),
        "draft_push_result": str(task_dir / "draft_push_result.json"),
        "publish_status": publish_result["status"],
    }
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="公众号两阶段生成脚本")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="只生成风格建议与大纲")
    prepare.add_argument("--topic", required=True, help="文章主题")
    prepare.add_argument("--audience", default="教育行业内容负责人", help="目标读者")
    prepare.add_argument("--writing-style", default=None, help="指定文风")
    prepare.add_argument("--dry-run", action="store_true", help="使用本地 stub 数据")

    produce = subparsers.add_parser("produce", help="生成正文、配图和草稿结果")
    produce.add_argument("--task-dir", required=True, help="prepare 阶段生成的任务目录")
    produce.add_argument("--outline-approved", action="store_true", help="显式确认已审核大纲")
    produce.add_argument("--publish-draft", action="store_true", help="尝试推送公众号草稿")
    produce.add_argument("--dry-run", action="store_true", help="使用本地 stub 数据")

    full = subparsers.add_parser("full", help="prepare + produce")
    full.add_argument("--topic", required=True, help="文章主题")
    full.add_argument("--audience", default="教育行业内容负责人", help="目标读者")
    full.add_argument("--writing-style", default=None, help="指定文风")
    full.add_argument("--outline-approved", action="store_true", help="显式确认已审核大纲")
    full.add_argument("--publish-draft", action="store_true", help="尝试推送公众号草稿")
    full.add_argument("--dry-run", action="store_true", help="使用本地 stub 数据")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "prepare":
            result = run_prepare(args)
        elif args.command == "produce":
            result = run_produce(args)
        else:
            prepare_result = run_prepare(args)
            if not args.outline_approved:
                raise RuntimeError("full 模式也必须显式传入 --outline-approved。")
            produce_args = argparse.Namespace(
                task_dir=prepare_result["task_dir"],
                config=args.config,
                outline_approved=True,
                publish_draft=args.publish_draft,
                dry_run=args.dry_run,
            )
            result = run_produce(produce_args)
            result["prepare_task_dir"] = prepare_result["task_dir"]
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (RuntimeError, FileNotFoundError, LLMConfigError) as exc:
        parser.exit(1, f"❌ {exc}\n")


if __name__ == "__main__":
    main()
