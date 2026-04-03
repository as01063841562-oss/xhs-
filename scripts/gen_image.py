#!/usr/bin/env python3
"""通用生图工具。

支持两类后端：
- `openai_compatible`：标准 OpenAI 兼容图片 API
- `gemini_web`：本机 Chrome + Gemini 网页自动化生图

所有参数从 config.yaml 和风格配置读取。
"""

import argparse
import base64
import os
import sys
from pathlib import Path
import requests
import yaml
from PIL import Image
from io import BytesIO

from common import config_state, is_placeholder
from gemini_web_image import (
    browser_image_ready,
    generate_placeholder_image,
    render_gemini_web_image,
)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT_DIR, "config")
STYLES_DIR = os.path.join(ROOT_DIR, "styles", "image")

# API 支持的 size 参数（保守列表，兼容 nano-banana-pro）
SUPPORTED_SIZES = [
    ("1024x1024", 1.0),       # 1:1
    ("1536x1024", 1.5),       # 3:2 横向
    ("1024x1536", 0.667),     # 2:3 竖向
]


def load_config():
    config_path = os.path.join(CONFIG_DIR, "config.yaml")
    if not os.path.exists(config_path):
        raise FileNotFoundError("请先创建 config/config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_image_style(style_name=None):
    if not style_name:
        config = load_config()
        style_name = config.get("defaults", {}).get("image_style", "hand_drawn")

    style_path = os.path.join(STYLES_DIR, f"{style_name}.yaml")
    if not os.path.exists(style_path):
        style_path = os.path.join(STYLES_DIR, "_presets", f"{style_name}.yaml")
    if not os.path.exists(style_path):
        raise FileNotFoundError(f"找不到配图风格: {style_name}")

    with open(style_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def pick_best_api_size(target_w, target_h):
    """根据目标尺寸选择最接近的 API 支持的 size 参数"""
    target_ratio = target_w / target_h
    best_size = "1024x1024"
    best_diff = float("inf")
    for size_str, ratio in SUPPORTED_SIZES:
        diff = abs(ratio - target_ratio)
        if diff < best_diff:
            best_diff = diff
            best_size = size_str
    return best_size


def generate_image(prompt, size="1024x1024", config=None):
    """调用 OpenAI 兼容接口生成图片"""
    if not config:
        config = load_config()

    api_config = config.get("image_api", {})
    base_url = api_config.get("base_url", "https://api.openai.com").rstrip("/")
    api_key = api_config.get("api_key", "")
    model = api_config.get("model", "dall-e-3")
    proxy = api_config.get("proxy", "")
    timeout = api_config.get("timeout", 60)

    if config_state(api_key) != "ready":
        raise ValueError("请在 config.yaml 中配置 image_api.api_key")

    url = f"{base_url}/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": "hd",
        "n": 1,
    }

    proxies = {"http": proxy, "https": proxy} if proxy else None

    resp = requests.post(url, json=data, headers=headers,
                         proxies=proxies, timeout=timeout)
    resp.raise_for_status()
    result = resp.json()

    if "data" not in result or len(result["data"]) == 0:
        raise Exception(f"API 返回格式错误: {result}")

    item = result["data"][0]
    return item.get("url") or item.get("b64_json")


def download_and_resize(image_url, target_size, proxy=""):
    """下载图片并缩放到目标尺寸（等比缩放+padding，不裁剪）"""
    proxies = {"http": proxy, "https": proxy} if proxy else None
    if isinstance(image_url, str) and image_url.startswith(("http://", "https://")):
        resp = requests.get(image_url, proxies=proxies, timeout=30)
        resp.raise_for_status()
        content = resp.content
    else:
        raw = image_url.split(",", 1)[1] if isinstance(image_url, str) and image_url.startswith("data:") and "," in image_url else image_url
        try:
            content = base64.b64decode(raw)
        except Exception as exc:
            raise ValueError(f"无法识别的图片数据: {str(image_url)[:120]}") from exc

    img = Image.open(BytesIO(content))
    tw, th = target_size

    # 等比缩放，让图片完整填入目标尺寸（可能有轻微裁剪边缘）
    img_ratio = img.width / img.height
    target_ratio = tw / th

    # 如果比例非常接近（差距<5%），直接 resize
    if abs(img_ratio - target_ratio) / target_ratio < 0.05:
        img = img.resize(target_size, Image.Resampling.LANCZOS)
    else:
        # 用 cover 模式：缩放到刚好覆盖目标，裁掉最少的部分
        if img_ratio > target_ratio:
            new_width = int(img.height * target_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            new_height = int(img.width / target_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))
        img = img.resize(target_size, Image.Resampling.LANCZOS)

    return img


def build_prompt(topic, image_type, style, target_w, target_h):
    """构建 prompt，包含精确的尺寸和构图指令"""
    tmpl = style.get("prompt_template", {})

    # 构图描述
    ratio = target_w / target_h
    if ratio > 2.0:
        composition = f"Ultra-wide horizontal banner ({target_w}x{target_h}), all content must fit within frame, no cropping needed"
    elif ratio > 1.3:
        composition = f"Wide horizontal composition ({target_w}x{target_h}), landscape format, all content must be fully visible"
    elif ratio < 0.8:
        composition = f"Tall vertical composition ({target_w}x{target_h}), portrait format"
    else:
        composition = f"Square composition ({target_w}x{target_h})"

    prompt_parts = [
        f"Topic: {topic}.",
        f"Style: {tmpl.get('style', '')}.",
        f"Elements: {tmpl.get('elements', '')}.",
        f"Background: {tmpl.get('background', '')}.",
        f"Color scheme: {tmpl.get('color_scheme', '')}.",
        f"Composition: {composition}.",
        "Important: all elements must be fully contained within the image, no content cut off at edges.",
    ]

    negative = tmpl.get("negative", "")
    if negative:
        prompt_parts.append(f"Avoid: {negative}.")

    return " ".join(prompt_parts)


def gen_image(topic, image_type="illustration", style_name=None, output="output.png"):
    """完整的图片生成流程"""
    config = load_config()
    style = load_image_style(style_name)

    # 获取目标尺寸
    sizes = style.get("sizes", {})
    size_config = sizes.get(image_type, {"width": 1024, "height": 768})
    target_w = size_config["width"]
    target_h = size_config["height"]

    # 选择最接近的 API size
    api_size = pick_best_api_size(target_w, target_h)

    # 构建 prompt（带尺寸信息）
    prompt = build_prompt(topic, image_type, style, target_w, target_h)
    print(f"🎨 生成 {image_type}: {topic}")
    print(f"📐 目标: {target_w}x{target_h} → API size: {api_size}")
    print(f"📝 Prompt: {prompt[:100]}...")

    backend = config.get("image_api", {}).get("backend", "openai_compatible")
    target_size = (target_w, target_h)
    browser_settings = config.get("browser_image", {})

    if backend == "gemini_web":
        print("🌐 后端: Gemini 网页自动化")
        try:
            render_gemini_web_image(prompt, output, target_size, settings=browser_settings)
            print(f"💾 已保存: {output} ({target_w}x{target_h})")
            return output
        except Exception as exc:
            print(f"  ⚠️  Gemini 网页生图失败，回退占位图: {exc}")
            generate_placeholder_image(Path(output), prompt, target_size)
            print(f"💾 已保存占位图: {output} ({target_w}x{target_h})")
            return output

    # 默认：OpenAI 兼容接口
    image_url = generate_image(prompt, size=api_size, config=config)
    if not image_url:
        raise Exception("图片生成失败")
    print(f"✅ 图片已生成")

    # 下载并调整尺寸
    proxy = config.get("image_api", {}).get("proxy", "")
    img = download_and_resize(image_url, target_size, proxy)

    # 保存
    img.save(output, "PNG", optimize=True)
    print(f"💾 已保存: {output} ({target_w}x{target_h})")

    return output


def image_backend_ready(config):
    """检查图片后端是否就绪"""
    try:
        api_config = config.get("image_api", {})
        backend = api_config.get("backend", "openai_compatible")
        if backend == "gemini_web":
            return browser_image_ready(config.get("browser_image", {}))
        api_key = api_config.get("api_key", "")
        model = api_config.get("model", "")
        base_url = api_config.get("base_url", "")
        return (
            config_state(api_key) == "ready"
            and config_state(model) == "ready"
            and not is_placeholder(base_url)
        )
    except Exception:
        return False


def render_image_to_path(prompt, output_path, size, config=None):
    """渲染图片到指定路径"""
    if not config:
        config = load_config()

    target_w, target_h = size
    backend = config.get("image_api", {}).get("backend", "openai_compatible")
    browser_settings = config.get("browser_image", {})
    if backend == "gemini_web":
        try:
            print("  🌐 后端: Gemini 网页自动化")
            render_gemini_web_image(prompt, output_path, size, settings=browser_settings)
            print(f"  ✅ Gemini 网页图片已保存: {output_path}")
            return output_path
        except Exception as exc:
            print(f"  ⚠️  Gemini 网页生图失败，回退占位图: {exc}")
            generate_placeholder_image(Path(output_path), prompt, size)
            print(f"  📁 占位图已保存: {output_path}")
            return output_path

    # 选择最接近的 API size
    api_size = pick_best_api_size(target_w, target_h)

    # 生成图片
    image_url = generate_image(prompt, size=api_size, config=config)
    if not image_url:
        raise Exception("图片生成失败")
    
    # 下载并调整尺寸
    proxy = config.get("image_api", {}).get("proxy", "")
    target_size = (target_w, target_h)
    img = download_and_resize(image_url, target_size, proxy)
    
    # 保存
    img.save(output_path, "PNG", optimize=True)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="公众号配图生成器")
    parser.add_argument("topic", help="图片主题描述")
    parser.add_argument("--type", choices=["cover", "illustration", "thumbnail"],
                        default="illustration", help="图片类型")
    parser.add_argument("--style", default=None, help="配图风格名称")
    parser.add_argument("--output", "-o", default="output.png", help="输出文件名")

    args = parser.parse_args()
    gen_image(args.topic, args.type, args.style, args.output)


if __name__ == "__main__":
    main()
