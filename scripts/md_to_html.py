#!/usr/bin/env python3
"""
Markdown → 公众号 HTML 转换器
根据排版风格配置生成 inline-style 的 HTML
公众号只支持 inline style，不支持 class 和外部 CSS
"""

import argparse
import os
import re
import sys
import yaml

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLES_DIR = os.path.join(ROOT_DIR, "styles", "layout")
CONFIG_DIR = os.path.join(ROOT_DIR, "config")


def load_config():
    config_path = os.path.join(CONFIG_DIR, "config.yaml")
    if not os.path.exists(config_path):
        raise FileNotFoundError("请先创建 config/config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_layout_style(style_name=None):
    """加载排版风格"""
    if not style_name:
        config = load_config()
        style_name = config.get("defaults", {}).get("layout_style", "blue_dot")

    style_path = os.path.join(STYLES_DIR, f"{style_name}.yaml")
    if not os.path.exists(style_path):
        style_path = os.path.join(STYLES_DIR, "_presets", f"{style_name}.yaml")
    if not os.path.exists(style_path):
        raise FileNotFoundError(f"找不到排版风格: {style_name}")

    with open(style_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_section_title_html(title_text, index, css_config):
    """根据标题样式类型生成 ## 大章节标题 HTML"""
    title_css = css_config.get("section_title", {})
    style_type = title_css.get("style", "bold_large")
    color = title_css.get("color", "#333")
    font_size = title_css.get("font_size", "18px")
    margin_top = title_css.get("margin_top", "40px")
    margin_bottom = title_css.get("margin_bottom", "20px")

    if style_type == "centered_number":
        dot_color = title_css.get("dot_color", color)
        return (
            f'<p style="text-align:center;margin-top:{margin_top};margin-bottom:8px;">'
            f'<span style="color:{dot_color};font-size:10px;">●</span></p>\n'
            f'<p style="text-align:center;font-size:28px;font-weight:bold;color:{color};'
            f'margin-bottom:5px;">{index:02d}</p>\n'
            f'<p style="text-align:center;font-size:{font_size};font-weight:bold;color:{color};'
            f'margin-bottom:{margin_bottom};">{title_text}</p>'
        )
    elif style_type == "left_bar":
        bar_color = title_css.get("bar_color", color)
        bar_width = title_css.get("bar_width", "4px")
        return (
            f'<p style="border-left:{bar_width} solid {bar_color};padding-left:12px;'
            f'font-size:{font_size};font-weight:bold;color:{color};'
            f'margin-top:{margin_top};margin-bottom:{margin_bottom};">'
            f'{title_text}</p>'
        )
    elif style_type == "icon_prefix":
        return (
            f'<p style="font-size:{font_size};font-weight:bold;color:{color};'
            f'margin-top:{margin_top};margin-bottom:{margin_bottom};">'
            f'▎{title_text}</p>'
        )
    else:  # bold_large
        return (
            f'<p style="font-size:{font_size};font-weight:bold;color:{color};'
            f'margin-top:{margin_top};margin-bottom:{margin_bottom};">'
            f'{title_text}</p>'
        )


def build_sub_title_html(title_text, css_config):
    """生成 ### 子标题 HTML — 轻量加粗，不编号不居中"""
    sub_css = css_config.get("sub_title", {})
    color = sub_css.get("color", "#333")
    font_size = sub_css.get("font_size", "17px")
    font_weight = sub_css.get("font_weight", "bold")
    margin_top = sub_css.get("margin_top", "28px")
    margin_bottom = sub_css.get("margin_bottom", "12px")
    return (
        f'<p style="font-size:{font_size};font-weight:{font_weight};color:{color};'
        f'margin-top:{margin_top};margin-bottom:{margin_bottom};">'
        f'{title_text}</p>'
    )


def build_body_style(css_config):
    """构建正文容器样式"""
    body = css_config.get("body", {})
    return (
        f'font-size:{body.get("font_size", "16px")};'
        f'line-height:{body.get("line_height", "1.8")};'
        f'color:{body.get("color", "#333")};'
        f'font-family:{body.get("font_family", "sans-serif")};'
        f'padding:{body.get("padding", "0 10px")};'
    )


def build_paragraph_style(css_config):
    """构建段落样式"""
    para = css_config.get("paragraph", {})
    return (
        f'margin-bottom:{para.get("margin_bottom", "20px")};'
        f'text-indent:{para.get("text_indent", "0")};'
    )


def md_to_html(md_text, style_name=None, image_urls=None):
    """
    将 Markdown 转换为公众号 HTML
    
    参数:
        md_text: Markdown 文本
        style_name: 排版风格名称
        image_urls: dict，key 是原始图片路径，value 是 mmbiz URL
    """
    style = load_layout_style(style_name)
    css = style.get("css", {})
    image_urls = image_urls or {}

    lines = md_text.strip().split("\n")
    html_parts = []
    section_index = 0
    in_blockquote = False
    blockquote_lines = []
    in_code_block = False
    code_lines = []
    code_lang = ""

    body_style = build_body_style(css)
    para_style = build_paragraph_style(css)

    # 包裹容器
    html_parts.append(f'<section style="{body_style}">')

    for line in lines:
        stripped = line.strip()

        # 代码块（``` 开始/结束）
        if stripped.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_lang = stripped[3:].strip()
                code_lines = []
            else:
                # 结束代码块，渲染
                code_css = css.get("code_block", {})
                bg = code_css.get("background", "#1e1e2e")
                text_color = code_css.get("color", "#cdd6f4")
                font_size = code_css.get("font_size", "13px")
                padding = code_css.get("padding", "16px 20px")
                border_radius = code_css.get("border_radius", "8px")
                line_height = code_css.get("line_height", "1.6")

                code_content = "\n".join(code_lines)
                # HTML 转义
                code_content = (code_content
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))

                html_parts.append(
                    f'<pre style="background:{bg};color:{text_color};'
                    f'font-size:{font_size};line-height:{line_height};'
                    f'padding:{padding};border-radius:{border_radius};'
                    f'overflow-x:auto;margin:20px 0;'
                    f'font-family:Consolas,Monaco,\'Courier New\',monospace;'
                    f'white-space:pre-wrap;word-wrap:break-word;">'
                    f'{code_content}</pre>'
                )
                in_code_block = False
                code_lines = []
                code_lang = ""
            continue

        if in_code_block:
            code_lines.append(line)  # 保留原始缩进
            continue

        # 空行
        if not stripped:
            if in_blockquote:
                # 结束引用块
                bq_css = css.get("blockquote", {})
                bq_style = (
                    f'border-left:3px solid {bq_css.get("border_left_color", "#ddd")};'
                    f'background:{bq_css.get("background", "#f9f9f9")};'
                    f'padding:{bq_css.get("padding", "15px 20px")};'
                    f'border-radius:{bq_css.get("border_radius", "4px")};'
                    f'margin-bottom:20px;'
                )
                content = "<br>".join(blockquote_lines)
                html_parts.append(f'<blockquote style="{bq_style}">{content}</blockquote>')
                blockquote_lines = []
                in_blockquote = False
            continue

        # 引用块
        if stripped.startswith(">"):
            in_blockquote = True
            blockquote_lines.append(stripped.lstrip("> ").strip())
            continue

        # ## 大章节标题
        h2_match = re.match(r'^##\s+(.+)$', stripped)
        if h2_match and not stripped.startswith("###"):
            section_index += 1
            title_text = h2_match.group(1).strip()
            html_parts.append(build_section_title_html(title_text, section_index, css))
            continue

        # ### 子标题（轻量加粗，不编号）
        h3_match = re.match(r'^###\s+(.+)$', stripped)
        if h3_match:
            title_text = h3_match.group(1).strip()
            html_parts.append(build_sub_title_html(title_text, css))
            continue

        # 一级标题（文章标题，通常不在正文中出现）
        h1_match = re.match(r'^#\s+(.+)$', stripped)
        if h1_match:
            title = h1_match.group(1).strip()
            html_parts.append(
                f'<p style="text-align:center;font-size:24px;font-weight:bold;'
                f'margin-bottom:30px;">{title}</p>'
            )
            continue

        # 图片
        img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
        if img_match:
            alt = img_match.group(1)
            src = img_match.group(2)
            # 替换为微信 CDN URL
            actual_src = image_urls.get(src, src)
            img_css = css.get("image", {})
            img_style = (
                f'border-radius:{img_css.get("border_radius", "8px")};'
                f'margin:{img_css.get("margin", "20px auto")};'
                f'max-width:{img_css.get("max_width", "100%")};'
                f'display:block;'
            )
            box_shadow = img_css.get("box_shadow", "")
            if box_shadow:
                img_style += f'box-shadow:{box_shadow};'
            html_parts.append(
                f'<p style="text-align:center;margin:20px 0;">'
                f'<img src="{actual_src}" alt="{alt}" style="{img_style}" /></p>'
            )
            continue

        # 分隔线
        if stripped in ("---", "***", "___"):
            divider = css.get("divider", {})
            d_style = divider.get("style", "solid")
            d_color = divider.get("color", "#eee")
            d_margin = divider.get("margin", "30px 0")
            html_parts.append(
                f'<hr style="border:none;border-top:1px {d_style} {d_color};margin:{d_margin};" />'
            )
            continue

        # 处理行内格式
        processed = process_inline(stripped, css)

        # 普通段落
        html_parts.append(f'<p style="{para_style}">{processed}</p>')

    # 关闭引用块（如果还在里面）
    if in_blockquote and blockquote_lines:
        bq_css = css.get("blockquote", {})
        bq_style = (
            f'border-left:3px solid {bq_css.get("border_left_color", "#ddd")};'
            f'background:{bq_css.get("background", "#f9f9f9")};'
            f'padding:{bq_css.get("padding", "15px 20px")};'
            f'border-radius:{bq_css.get("border_radius", "4px")};'
            f'margin-bottom:20px;'
        )
        content = "<br>".join(blockquote_lines)
        html_parts.append(f'<blockquote style="{bq_style}">{content}</blockquote>')

    html_parts.append('</section>')
    return "\n".join(html_parts)


def process_inline(text, css):
    """处理行内格式：加粗、高亮、链接、行内代码"""
    highlight = css.get("highlight", {})
    hl_color = highlight.get("color", "#1e6fff")
    hl_bold = highlight.get("bold", True)
    hl_bg = highlight.get("background", "")

    # **加粗** → 高亮样式
    def bold_replace(m):
        style = f'color:{hl_color};'
        if hl_bold:
            style += 'font-weight:bold;'
        if hl_bg:
            style += f'background:{hl_bg};padding:2px 4px;'
        return f'<span style="{style}">{m.group(1)}</span>'

    text = re.sub(r'\*\*([^*]+)\*\*', bold_replace, text)

    # *斜体*
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)

    # `行内代码`
    text = re.sub(
        r'`([^`]+)`',
        r'<code style="background:#f5f5f5;padding:2px 6px;border-radius:3px;'
        r'font-size:14px;font-family:Consolas,monospace;">\1</code>',
        text
    )

    # [链接](url)
    text = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        rf'<a style="color:{hl_color};text-decoration:none;" href="\2">\1</a>',
        text
    )

    return text


def main():
    parser = argparse.ArgumentParser(description="Markdown → 公众号 HTML 转换器")
    parser.add_argument("input", help="输入 Markdown 文件路径")
    parser.add_argument("--style", default=None, help="排版风格名称")
    parser.add_argument("--output", "-o", default=None, help="输出 HTML 文件路径")
    parser.add_argument("--image-map", default=None,
                        help="图片 URL 映射文件（YAML 格式，key=原始路径 value=mmbiz URL）")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ 文件不存在: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        md_text = f.read()

    # 加载图片映射
    image_urls = {}
    if args.image_map and os.path.exists(args.image_map):
        with open(args.image_map, "r", encoding="utf-8") as f:
            image_urls = yaml.safe_load(f) or {}

    html = md_to_html(md_text, args.style, image_urls)

    # 输出
    output_path = args.output or args.input.rsplit(".", 1)[0] + ".html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ 已转换: {args.input} → {output_path}")
    print(f"📐 排版风格: {args.style or '默认'}")


if __name__ == "__main__":
    main()
