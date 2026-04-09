#!/usr/bin/env python3
"""Analyze collected XHS reference samples and generate reusable style guides."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

import common
from xhs_customer_state import materials_gate_path

DEFAULT_CLIENT = "wuhan-tutoring"
IGNORED_TITLE_EXAMPLES = {"置顶"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Wuhan tutoring style guides from local references.")
    parser.add_argument("--client", default=DEFAULT_CLIENT)
    return parser.parse_args(argv)


def _extract_title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or None
    return None


def _extract_access_level(text: str) -> str | None:
    match = re.search(r"^- access_level:\s*(.+)$", text, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip() or None


def analyze_articles(article_dir: Path) -> dict[str, object]:
    docs: list[str] = []
    titles: list[str] = []
    access_levels: Counter[str] = Counter()
    lengths: list[int] = []

    for path in sorted(article_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        docs.append(text)
        lengths.append(len(text))

        title = _extract_title(text)
        if title and title not in IGNORED_TITLE_EXAMPLES:
            titles.append(title)

        access_level = _extract_access_level(text) or "unknown"
        access_levels[access_level] += 1

    sample_count = len(docs)
    full_note_count = access_levels.get("full_note", 0)
    profile_card_count = access_levels.get("profile_card", 0)
    avg_length = int(sum(lengths) / sample_count) if sample_count else 0

    return {
        "sample_count": sample_count,
        "full_note_count": full_note_count,
        "profile_card_count": profile_card_count,
        "avg_length": avg_length,
        "title_examples": titles[:10],
        "access_levels": dict(access_levels),
    }


def analyze_images(image_dir: Path) -> dict[str, object]:
    palette: Counter[tuple[int, int, int]] = Counter()
    sizes: list[list[int]] = []

    for path in sorted(image_dir.glob("*")):
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            sizes.append([rgb.width, rgb.height])
            reduced = rgb.resize((32, 32))
            pixels = [
                reduced.getpixel((x, y))
                for y in range(reduced.height)
                for x in range(reduced.width)
            ]
            palette.update(pixels)

    return {
        "sample_count": len(sizes),
        "common_sizes": sizes[:10],
        "top_colors": [list(color) for color, _ in palette.most_common(8)],
    }


def render_writing_guide(article_report: dict[str, object]) -> str:
    sample_count = int(article_report.get("sample_count", 0))
    full_note_count = int(article_report.get("full_note_count", 0))
    profile_card_count = int(article_report.get("profile_card_count", 0))
    avg_length = int(article_report.get("avg_length", 0))
    title_examples = article_report.get("title_examples") or []

    lines = [
        "# 文案风格指南",
        "",
        f"- 样本总数：{sample_count}",
        f"- 正文级样本：{full_note_count}",
        f"- profile-card 快照：{profile_card_count}",
        f"- 平均文本长度：{avg_length}",
    ]

    if full_note_count < 3:
        lines.extend(
            [
                "",
                "## 当前判断边界",
                "- 当前可用样本仍以 profile-card 快照为主，缺少足够的正文级样本。",
                "- 不要把下面约束当成完整正文模板，它们更适合作为选题和标题层的临时参考。",
            ]
        )

    if title_examples:
        lines.extend(
            [
                "",
                "## 标题样本",
                *[f"- {title}" for title in title_examples[:5]],
            ]
        )

    lines.extend(
        [
            "",
            "## 可执行约束",
            "- 标题优先使用问题句、结果句或家长决策场景，不走空泛鸡汤表达。",
            "- 标题尽量直接点出武汉、本地升学、中考、规划、陪伴式服务等实际场景。",
            "- 如果后续拿到正文级样本，再补充开头钩子、段落结构、结尾 CTA 的稳定模板。",
            "- 现阶段不要假装已经归纳出完整正文节奏，只能先保留保守约束。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_image_guide(image_report: dict[str, object]) -> str:
    sample_count = int(image_report.get("sample_count", 0))
    common_sizes = image_report.get("common_sizes") or []
    top_colors = image_report.get("top_colors") or []

    lines = [
        "# 图片风格模板",
        "",
        f"- 样本数：{sample_count}",
        f"- 参考尺寸：{common_sizes}",
        f"- 主色参考：{top_colors}",
        "",
        "## 可执行约束",
        "- 封面优先使用高对比大标题，保留清晰主视觉，不要堆满装饰元素。",
        "- 正文配图优先讲解图和信息图，不做无信息量的花哨拼贴。",
        "- 重点词允许高亮，但单张图的信息块数量要可控，避免整页过密。",
        "- 后续如果补充更多样本，再细化字体、底色和版式偏好。",
    ]
    return "\n".join(lines) + "\n"


def compute_materials_ready(
    article_report: dict[str, object],
    image_report: dict[str, object],
) -> bool:
    return bool(
        int(article_report.get("sample_count", 0)) >= 3
        and int(article_report.get("full_note_count", 0)) >= 3
        and int(image_report.get("sample_count", 0)) >= 3
    )


def generate_style_guides(client_slug: str = DEFAULT_CLIENT) -> dict[str, Any]:
    refs_dir = common.get_client_root(client_slug) / "references"
    article_dir = refs_dir / "article"
    image_dir = refs_dir / "images"

    article_report = analyze_articles(article_dir)
    image_report = analyze_images(image_dir)
    materials_ready = compute_materials_ready(article_report, image_report)

    common.save_text_file(
        refs_dir / "文案风格指南.md",
        render_writing_guide(article_report),
    )
    common.save_text_file(
        refs_dir / "图片风格模板.md",
        render_image_guide(image_report),
    )
    common.save_json_file(
        materials_gate_path(client_slug),
        {
            "materials_ready": materials_ready,
            "article_sample_count": int(article_report.get("sample_count", 0)),
            "full_note_count": int(article_report.get("full_note_count", 0)),
            "image_sample_count": int(image_report.get("sample_count", 0)),
            "updated_at": common.timestamp(),
        },
    )

    return {
        "client": client_slug,
        "article_report": article_report,
        "image_report": image_report,
        "materials_ready": materials_ready,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = generate_style_guides(args.client)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
