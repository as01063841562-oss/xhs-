#!/usr/bin/env python3
"""生成小红书图文素材包。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import load_config, make_run_dir, save_json_file, save_text_file
from gen_image import image_backend_ready, render_image_to_path
from llm_client import LLMConfigError, OpenAICompatibleLLM


def llm_client(config: dict[str, Any], dry_run: bool) -> OpenAICompatibleLLM | None:
    client = OpenAICompatibleLLM(config)
    if dry_run:
        return None
    client.require_ready()
    return client


def stub_payload(topic: str, audience: str) -> dict[str, Any]:
    return {
        "positioning": f"面向 {audience} 的教育自媒体效率提升内容",
        "cover_title": "AI 帮你省下内容时间",
        "cover_prompt": f"为小红书封面创作一张 3:4 竖版海报，主题是：{topic}，风格清爽、专业、适合教育行业运营者。",
        "hashtags": [
            "教育行业AI",
            "自媒体运营",
            "公众号运营",
            "小红书运营",
            "AI提效",
            "内容自动化",
            "教培增长",
            "运营提效",
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


def load_payload_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"找不到素材包文件: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"素材包文件不是合法 JSON: {path}") from exc

    required = (
        "positioning",
        "cover_title",
        "cover_prompt",
        "hashtags",
        "publish_checklist",
        "variants",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"素材包文件缺少字段: {', '.join(missing)}")
    return payload


def build_prompts(topic: str, audience: str, style_name: str) -> tuple[str, str]:
    system = (
        "你是一名擅长教育行业内容增长的小红书策划。"
        "请输出严格 JSON，字段必须包含：positioning, cover_title, cover_prompt, hashtags, publish_checklist, variants。"
        "variants 必须有 3 条，每条包含 title, body, angle。"
    )
    user = (
        f"主题：{topic}\n"
        f"目标读者：{audience}\n"
        f"风格偏好：{style_name}\n"
        "要求：\n"
        "1. 文案适合人工复审后直接发布。\n"
        "2. 标签控制在 8-12 个。\n"
        "3. 封面标题不超过 16 个字。\n"
        "4. 不能承诺自动发帖或绕过平台风控。\n"
    )
    return system, user


def render_variants_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['positioning']}",
        "",
        f"**封面标题建议**：{payload['cover_title']}",
        "",
        "## 文案版本",
        "",
    ]
    for index, variant in enumerate(payload["variants"], start=1):
        lines.append(f"## 版本 {index}｜{variant['title']}")
        lines.append("")
        lines.append(f"**切入角度**：{variant['angle']}")
        lines.append("")
        lines.append(variant["body"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_cover_png(path: Path, width: int, height: int, title: str) -> None:
    image = Image.new("RGB", (width, height), color=(255, 246, 236))
    draw = ImageDraw.Draw(image)
    draw.rectangle((32, 32, width - 32, height - 32), outline=(255, 140, 72), width=6)

    def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
        for candidate in candidates:
            font_path = Path(candidate)
            if font_path.exists():
                try:
                    return ImageFont.truetype(str(font_path), size=size)
                except OSError:
                    continue
        return ImageFont.load_default()

    def wrap_title(text: str, chunk_size: int = 8) -> str:
        cleaned = text.strip()
        if len(cleaned) <= chunk_size:
            return cleaned
        return "\n".join(
            cleaned[index : index + chunk_size]
            for index in range(0, len(cleaned), chunk_size)
        )

    title_font = load_font(72)
    label_font = load_font(28)
    draw.multiline_text((60, 84), wrap_title(title[:28]), fill=(102, 63, 24), font=title_font, spacing=12)
    draw.text((60, 248), "素材包预览图", fill=(153, 109, 62), font=label_font)
    image.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成小红书素材包")
    parser.add_argument("--topic", required=True, help="主题")
    parser.add_argument("--audience", default="教育行业运营负责人", help="目标人群")
    parser.add_argument("--style", default="干货型", help="风格偏好")
    parser.add_argument("--render-cover", action="store_true", help="尝试生成封面图")
    parser.add_argument(
        "--payload-file",
        default=None,
        help="从本地 JSON 文件读取素材包，跳过模型调用",
    )
    parser.add_argument("--dry-run", action="store_true", help="使用本地 stub 数据")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        if args.payload_file:
            payload = load_payload_file(Path(args.payload_file))
        else:
            client = llm_client(config, args.dry_run)
            if client is None:
                payload = stub_payload(args.topic, args.audience)
            else:
                system, user = build_prompts(args.topic, args.audience, args.style)
                payload = client.chat_json(system, user, temperature=0.7)

        run_dir = make_run_dir("xhs", args.topic)
        save_json_file(run_dir / "task.json", payload)
        save_text_file(run_dir / "note_variants.md", render_variants_markdown(payload))
        save_text_file(run_dir / "cover_title.txt", payload["cover_title"] + "\n")
        save_text_file(run_dir / "cover_prompt.txt", payload["cover_prompt"] + "\n")
        with (run_dir / "hashtags.yaml").open("w", encoding="utf-8") as handle:
            yaml.safe_dump(payload["hashtags"], handle, allow_unicode=True, sort_keys=False)
        save_text_file(
            run_dir / "publish_checklist.md",
            "# 发布检查清单\n\n" + "\n".join(f"- {item}" for item in payload["publish_checklist"]) + "\n",
        )

        cover_path = None
        if args.render_cover:
            width = int(config.get("xhs", {}).get("cover_width", 1080))
            height = int(config.get("xhs", {}).get("cover_height", 1440))
            cover_path = run_dir / "cover.png"
            if args.dry_run or not image_backend_ready(config):
                render_cover_png(cover_path, width, height, payload["cover_title"])
            else:
                render_image_to_path(
                    payload["cover_prompt"],
                    str(cover_path),
                    (width, height),
                    config=config,
                )

        summary = {
            "status": "ok",
            "task_dir": str(run_dir),
            "note_variants": str(run_dir / "note_variants.md"),
            "hashtags": str(run_dir / "hashtags.yaml"),
            "cover_title": str(run_dir / "cover_title.txt"),
            "cover_prompt": str(run_dir / "cover_prompt.txt"),
            "publish_checklist": str(run_dir / "publish_checklist.md"),
        }
        if cover_path:
            summary["cover_image"] = str(cover_path)

        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
    except (RuntimeError, FileNotFoundError, LLMConfigError) as exc:
        parser.exit(1, f"❌ {exc}\n")


if __name__ == "__main__":
    main()
