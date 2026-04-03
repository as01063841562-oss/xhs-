#!/usr/bin/env python3
"""
配图 Prompt 智能生成器
读取文章 Markdown，分析每个插图位置的上下文，
结合配图风格（插图）和头图风格（封面）生成针对性的 prompt。

用法:
  python3 gen_image_prompts.py article.md [-s ai_play] [-c ai_play] [-o output/image_prompts.yaml]

  -s / --style    插图风格（styles/image/ 下）
  -c / --cover    头图风格（styles/cover/ 下）

输入文章中用 ![描述](placeholder) 标记插图位置。
第一张自动作为头图，其余为插图。
"""

import argparse
import os
import re
import sys
import yaml

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_STYLES_DIR = os.path.join(ROOT_DIR, "styles", "image")
COVER_STYLES_DIR = os.path.join(ROOT_DIR, "styles", "cover")
CONFIG_DIR = os.path.join(ROOT_DIR, "config")


def load_config():
    config_path = os.path.join(CONFIG_DIR, "config.yaml")
    if not os.path.exists(config_path):
        raise FileNotFoundError("请先创建 config/config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_style(styles_dir, style_name, fallback_name, config_key):
    """通用风格加载：先找自定义，再找 _presets/"""
    if not style_name:
        config = load_config()
        style_name = config.get("defaults", {}).get(config_key, fallback_name)

    style_path = os.path.join(styles_dir, f"{style_name}.yaml")
    if not os.path.exists(style_path):
        style_path = os.path.join(styles_dir, "_presets", f"{style_name}.yaml")
    if not os.path.exists(style_path):
        raise FileNotFoundError(f"找不到风格: {style_name} (在 {styles_dir})")

    with open(style_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_image_style(style_name=None):
    return _load_style(IMAGE_STYLES_DIR, style_name, "ai_play", "image_style")


def load_cover_style(style_name=None):
    return _load_style(COVER_STYLES_DIR, style_name, "ai_play", "cover_style")


def extract_image_slots(md_text):
    """从 Markdown 中提取插图位置信息"""
    plain_text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '{{IMG}}', md_text)

    slots = []
    pattern = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

    img_index = 0
    for match in pattern.finditer(md_text):
        alt = match.group(1)

        img_positions = [m.start() for m in re.finditer(r'\{\{IMG\}\}', plain_text)]
        if img_index < len(img_positions):
            plain_pos = img_positions[img_index]
        else:
            plain_pos = match.start()

        clean = re.sub(r'\{\{IMG\}\}', '', plain_text)
        offset = img_index * 7
        adjusted_pos = max(0, plain_pos - offset)

        ctx_before = clean[max(0, adjusted_pos - 500):adjusted_pos].strip()
        ctx_after = clean[adjusted_pos:adjusted_pos + 500].strip()

        for p in [r'#{1,3}\s+', r'\*\*([^*]+)\*\*', r'\*([^*]+)\*', r'`[^`]+`', r'>\s+']:
            ctx_before = re.sub(p, r'\1' if '(' in p else '', ctx_before)
            ctx_after = re.sub(p, r'\1' if '(' in p else '', ctx_after)

        slots.append({
            "alt": alt,
            "context_before": ctx_before[-300:],
            "context_after": ctx_after[:300],
        })
        img_index += 1

    return slots


def generate_cover_prompt(slot, cover_style, article_title=""):
    """根据头图风格生成封面 prompt"""
    tmpl = cover_style.get("prompt_template", {})
    sizes = cover_style.get("sizes", {})
    size_cfg = sizes.get("cover_large", {"width": 900, "height": 383})

    # 内容描述：优先用文章标题，其次用 alt
    content = article_title or slot["alt"] or "article cover"

    parts = [
        f"Cover image for article: {content}",
        tmpl.get("style", ""),
        tmpl.get("text_element", ""),
        tmpl.get("icon_element", ""),
        tmpl.get("composition", ""),
    ]
    prompt = ", ".join(p for p in parts if p)
    negative = tmpl.get("negative", "")

    return prompt, negative, size_cfg


def generate_illustration_prompt(slot, image_style):
    """根据插图风格生成文章内配图 prompt"""
    tmpl = image_style.get("prompt_template", {})
    sizes = image_style.get("sizes", {})
    size_cfg = sizes.get("illustration", {"width": 1024, "height": 768})

    content_desc = slot["alt"]
    if not content_desc or content_desc == "placeholder":
        context = slot["context_before"] + " " + slot["context_after"]
        content_desc = context[:100].strip()

    parts = [
        content_desc,
        tmpl.get("style", ""),
        tmpl.get("elements", ""),
        tmpl.get("background", ""),
        tmpl.get("color_scheme", ""),
        "4:3 aspect ratio, informative illustration",
    ]
    prompt = ". ".join(p for p in parts if p)
    negative = tmpl.get("negative", "")

    return prompt, negative, size_cfg


def extract_title(md_text):
    """尝试从 Markdown 中提取文章标题（# 一级标题）"""
    m = re.search(r'^#\s+(.+)$', md_text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def main():
    parser = argparse.ArgumentParser(description="配图 Prompt 智能生成器")
    parser.add_argument("input", help="文章 Markdown 文件")
    parser.add_argument("-s", "--style", default=None, help="插图风格名称（styles/image/）")
    parser.add_argument("-c", "--cover", default=None, help="头图风格名称（styles/cover/）")
    parser.add_argument("-t", "--title", default=None, help="文章标题（用于头图 prompt）")
    parser.add_argument("-o", "--output", default=None, help="输出 YAML 路径")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ 文件不存在: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        md_text = f.read()

    image_style = load_image_style(args.style)
    cover_style = load_cover_style(args.cover)
    article_title = args.title or extract_title(md_text)

    slots = extract_image_slots(md_text)

    if not slots:
        print("⚠️ 文章中没有找到插图标记 ![描述](placeholder)")
        print("   请在需要插图的位置添加 ![图片描述](placeholder)")
        sys.exit(0)

    results = []

    for i, slot in enumerate(slots):
        is_cover = (i == 0)

        if is_cover:
            prompt, negative, size_cfg = generate_cover_prompt(slot, cover_style, article_title)
            img_type = "cover"
        else:
            prompt, negative, size_cfg = generate_illustration_prompt(slot, image_style)
            img_type = "illustration"

        results.append({
            "index": i,
            "type": img_type,
            "size": f"{size_cfg['width']}x{size_cfg['height']}",
            "width": size_cfg["width"],
            "height": size_cfg["height"],
            "prompt": prompt,
            "negative": negative,
            "context": slot["alt"] or "(从上下文提取)",
            "filename": "cover.png" if is_cover else f"ill_{i}.png",
        })

    # 输出
    output_path = args.output or os.path.join(ROOT_DIR, "output", "image_prompts.yaml")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(results, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"✅ 生成 {len(results)} 个配图 prompt")
    print(f"📁 输出: {output_path}")
    print(f"🖼️ 头图风格: {cover_style.get('name', '默认')}")
    print(f"🎨 插图风格: {image_style.get('name', '默认')}")
    print()
    for r in results:
        tag = "🖼️ 头图" if r["type"] == "cover" else f"📷 插图{r['index']}"
        print(f"  {tag} ({r['size']}) → {r['filename']}")
        print(f"    {r['prompt'][:80]}...")
        print()


if __name__ == "__main__":
    main()
