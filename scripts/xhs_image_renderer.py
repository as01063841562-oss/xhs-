#!/usr/bin/env python3
"""小红书图片渲染引擎。

使用 Playwright 将 HTML 模板渲染为 1080×1440 的高质量图片。
支持 4 种模板：data_table, info_card, comparison, timeline。
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _load_template(style: str) -> str:
    """加载 HTML 模板文件。"""
    path = TEMPLATE_DIR / f"{style}.html"
    if not path.exists():
        raise FileNotFoundError(f"模板不存在: {path}")
    return path.read_text(encoding="utf-8")


def _esc(text: str) -> str:
    """HTML 转义。"""
    return html.escape(str(text))


def _render_tags(tags: list[str]) -> str:
    """渲染标签 HTML。"""
    return "".join(f'<span class="tag">#{_esc(t)}</span>' for t in tags[:8])


def build_data_table_html(topic: dict[str, Any]) -> str:
    """构建数据表格类图片的 HTML。"""
    tpl = _load_template("data_table")
    data = topic.get("data_content", {})
    headers = "".join(f"<th>{_esc(h)}</th>" for h in data.get("headers", []))
    rows = ""
    for row in data.get("rows", []):
        cells = "".join(f"<td>{_esc(c)}</td>" for c in row)
        rows += f"<tr>{cells}</tr>"
    tags_html = _render_tags(topic.get("tags", []))
    return (
        tpl.replace("{{TITLE}}", _esc(topic["title"]))
        .replace("{{SUBTITLE}}", _esc(topic.get("subtitle", "")))
        .replace("{{TABLE_TITLE}}", _esc(data.get("table_title", "")))
        .replace("{{TABLE_HEADERS}}", headers)
        .replace("{{TABLE_ROWS}}", rows)
        .replace("{{TAGS}}", tags_html)
    )


def build_info_card_html(topic: dict[str, Any]) -> str:
    """构建知识点卡片类图片的 HTML。"""
    tpl = _load_template("info_card")
    points = topic.get("key_points", [])
    points_html = ""
    for i, point in enumerate(points, 1):
        points_html += f'''
        <div class="point-card">
            <div class="point-number">{i}</div>
            <div class="point-text">{_esc(point)}</div>
        </div>'''
    tags_html = _render_tags(topic.get("tags", []))
    return (
        tpl.replace("{{TITLE}}", _esc(topic["title"]))
        .replace("{{SUBTITLE}}", _esc(topic.get("subtitle", "")))
        .replace("{{POINTS}}", points_html)
        .replace("{{TAGS}}", tags_html)
    )


def build_comparison_html(topic: dict[str, Any]) -> str:
    """构建对比类图片的 HTML。"""
    tpl = _load_template("comparison")
    data = topic.get("compare_data", {})
    items = data.get("items", [])

    left_items = ""
    right_items = ""
    center_labels = ""
    for item in items:
        left_items += f'''
        <div class="row-label">
            <div class="row-content">{_esc(item.get("left", ""))}</div>
        </div>'''
        right_items += f'''
        <div class="row-label">
            <div class="row-content">{_esc(item.get("right", ""))}</div>
        </div>'''
        center_labels += f'''
        <div class="center-label">
            <span class="center-icon">✅</span> {_esc(item.get("label", ""))}
        </div>'''

    tags_html = _render_tags(topic.get("tags", []))
    return (
        tpl.replace("{{TITLE}}", _esc(topic["title"]))
        .replace("{{SUBTITLE}}", _esc(topic.get("subtitle", "")))
        .replace("{{LEFT_TITLE}}", _esc(data.get("left_title", "A")))
        .replace("{{RIGHT_TITLE}}", _esc(data.get("right_title", "B")))
        .replace("{{LEFT_ITEMS}}", left_items)
        .replace("{{RIGHT_ITEMS}}", right_items)
        .replace("{{CENTER_LABELS}}", center_labels)
        .replace("{{TAGS}}", tags_html)
    )


def build_timeline_html(topic: dict[str, Any]) -> str:
    """构建时间线类图片的 HTML。"""
    tpl = _load_template("timeline")
    timeline_data = topic.get("timeline_data", [])
    items_html = ""
    for item in timeline_data:
        items_html += f'''
        <div class="timeline-item">
            <div class="timeline-month">{_esc(item.get("month", ""))}</div>
            <div class="timeline-dot"></div>
            <div class="timeline-content">
                <div class="timeline-title">{_esc(item.get("title", ""))}</div>
                <div class="timeline-desc">{_esc(item.get("desc", ""))}</div>
            </div>
        </div>'''
    tags_html = _render_tags(topic.get("tags", []))
    return (
        tpl.replace("{{TITLE}}", _esc(topic["title"]))
        .replace("{{SUBTITLE}}", _esc(topic.get("subtitle", "")))
        .replace("{{TIMELINE_ITEMS}}", items_html)
        .replace("{{TAGS}}", tags_html)
    )


# ── 模板路由 ────────────────────────────────────────────────

BUILDERS = {
    "data_table": build_data_table_html,
    "info_card": build_info_card_html,
    "comparison": build_comparison_html,
    "timeline": build_timeline_html,
}


def build_html(topic: dict[str, Any]) -> str:
    """根据 topic 的 style 字段自动选择模板并构建 HTML。"""
    style = topic.get("style", "info_card")
    builder = BUILDERS.get(style)
    if not builder:
        raise ValueError(f"不支持的图片风格: {style}，可选: {list(BUILDERS.keys())}")
    return builder(topic)


def render_image(
    topic: dict[str, Any],
    output_path: Path | str,
    width: int = 1080,
    height: int = 1440,
) -> Path:
    """将选题渲染为图片。

    使用 Playwright 截取 HTML 为 PNG。
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html_content = build_html(topic)

    # 保存 HTML 用于调试
    html_path = output_path.with_suffix(".html")
    html_path.write_text(html_content, encoding="utf-8")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html_content, wait_until="networkidle")
        # 等待字体加载
        page.wait_for_timeout(1000)
        page.screenshot(path=str(output_path), full_page=False)
        browser.close()

    print(f"  📸 图片已渲染: {output_path} ({output_path.stat().st_size // 1024}KB)")
    return output_path


def render_topic_images(
    topic: dict[str, Any],
    output_dir: Path | str,
    count: int = 3,
) -> list[Path]:
    """为一个选题渲染多张图片（封面+内容+CTA）。

    目前策略：
    - 图1：使用选题自带风格
    - 图2：如果有 data_content 就用 data_table，否则用 info_card
    - 图3：用 info_card 风格做总结CTA图
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    images: list[Path] = []

    # 图1：主图（封面）
    img1 = render_image(topic, output_dir / "slide_1.png")
    images.append(img1)

    if count >= 2:
        # 图2：补充内容图
        # 如果主图是 data_table，第2张用 info_card 补充关键点
        # 如果主图不是 data_table 但有 data_content，用 data_table
        topic2 = dict(topic)
        if topic.get("style") == "data_table" and topic.get("key_points"):
            topic2["style"] = "info_card"
        elif topic.get("style") != "data_table" and topic.get("data_content"):
            topic2["style"] = "data_table"
        elif topic.get("style") == "comparison":
            # 对比图第2张用 info_card 展示更多建议
            topic2["style"] = "info_card"
            if not topic2.get("key_points"):
                topic2["key_points"] = [
                    f"核心要点：{topic['title']}",
                    "建议收藏本图方便随时查阅",
                    "关注获取更多武汉本地升学干货",
                    "有疑问可在评论区留言",
                    "分享给需要的家长朋友",
                ]
        elif topic.get("style") == "timeline":
            topic2["style"] = "info_card"
            if not topic2.get("key_points"):
                events = topic.get("timeline_data", [])
                topic2["key_points"] = [f"{e['month']}：{e['title']}" for e in events[:6]]
                topic2["subtitle"] = "关键节点速查"

        img2 = render_image(topic2, output_dir / "slide_2.png")
        images.append(img2)

    if count >= 3:
        # 图3：CTA 总结图
        cta_topic = {
            "title": topic["title"],
            "subtitle": "收藏+关注·获取更多干货",
            "style": "info_card",
            "tags": topic.get("tags", []),
            "key_points": [
                "✅ 收藏本笔记，考前随时翻看",
                "✅ 关注账号，每日更新武汉升学干货",
                "✅ 评论区留言，免费获取完整资料",
                "✅ 分享给其他家长，一起备战中考",
                "✅ 点赞支持，激励我们持续更新",
            ],
        }
        img3 = render_image(cta_topic, output_dir / "slide_3.png")
        images.append(img3)

    return images


# ── CLI 测试入口 ────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from xhs_topic_generator import get_random_topics

    print("🎨 小红书图片渲染引擎测试")
    print("=" * 50)

    topics = get_random_topics(2)
    for topic in topics:
        print(f"\n📌 渲染: {topic['title']} (style={topic['style']})")
        output_dir = Path(__file__).resolve().parent.parent / "output" / "test_render" / topic["style"]
        images = render_topic_images(topic, output_dir, count=3)
        for img in images:
            print(f"  ✅ {img}")

    print("\n🎉 渲染测试完成")
