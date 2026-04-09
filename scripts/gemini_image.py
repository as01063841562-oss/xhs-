#!/usr/bin/env python3
"""Gemini 生图模块。

支持两种后端：
  1. `gemini_cli`：通过 gemini -p 命令行生成图片并保存
  2. `gemini_web`：通过本机 Chrome + Gemini 网页自动化生图
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import load_config, ensure_dir
from gemini_web_image import (
    browser_image_ready,
    render_gemini_web_image,
)


class GeminiImageError(RuntimeError):
    """Gemini 生图失败。"""


def generate_image(
    prompt: str,
    output_path: str | Path | None = None,
    config: dict[str, Any] | None = None,
    allow_placeholder: bool = True,
    reference_image_paths: list[str] | None = None,
) -> Path:
    """使用 Gemini CLI 生成图片。

    Args:
        prompt: 图片描述/提示词
        output_path: 输出文件路径，默认自动生成
        config: 项目配置

    Returns:
        生成图片的路径
    """
    if config is None:
        config = load_config()

    gem_cfg = config.get("gemini_image", {})
    backend = gem_cfg.get("backend", "gemini_cli")
    browser_settings = config.get("browser_image", {})
    gemini_cmd = gem_cfg.get("command", "/opt/homebrew/bin/gemini")
    model = gem_cfg.get("model", "gemini-2.5-flash")
    output_dir = Path(gem_cfg.get("output_dir", "/tmp/gemini_images"))
    timeout = gem_cfg.get("timeout", 180)
    ensure_dir(output_dir)

    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"gemini_{ts}.png"
    output_path = Path(output_path)
    ensure_dir(output_path.parent)

    print(f"  📝 提示词: {prompt[:80]}...")
    print(f"  📁 目标: {output_path}")

    if backend == "gemini_web":
        print("  🌐 后端: Gemini 网页自动化")
        size = (
            int(config.get("xhs", {}).get("cover_width", 1080)),
            int(config.get("xhs", {}).get("cover_height", 1440)),
        )
        if not browser_image_ready(browser_settings):
            if not allow_placeholder:
                raise GeminiImageError("Gemini 网页后端尚未就绪")
            print("  ⚠️  Gemini 网页后端尚未就绪，使用占位图")
            _generate_placeholder(output_path, prompt)
            return output_path
        try:
            render_gemini_web_image(
                prompt,
                output_path,
                size,
                settings=browser_settings,
                reference_image_paths=list(reference_image_paths or []),
            )
            print(f"  ✅ 图片已生成: {output_path}")
            return output_path
        except Exception as exc:
            if not allow_placeholder:
                raise GeminiImageError(f"Gemini 网页生图失败: {exc}") from exc
            print(f"  ⚠️  Gemini 网页生图失败，使用占位图: {exc}")
            _generate_placeholder(output_path, prompt)
            return output_path

    # 告诉 Gemini：生成图片 → 把文件保存到指定路径
    full_prompt = (
        f"根据以下描述，生成一张高质量的图片，然后将图片保存到文件 {output_path}\n\n"
        f"描述：{prompt}\n\n"
        f"要求：\n"
        f"- 图片比例 3:4 竖版（1080x1440 像素）\n"
        f"- 风格：专业、吸引眼球、适合社交媒体\n"
        f"- 直接用工具生成并保存图片文件，不需要输出任何其他说明"
    )

    print(f"  🎨 调用 Gemini CLI 生图...")

    try:
        # 记录开始前 output_dir 和 cwd 中已有的图片
        existing_images = set()
        for d in [output_dir, Path.cwd()]:
            existing_images.update(str(p) for p in d.glob("*.png") if p.is_file())
            existing_images.update(str(p) for p in d.glob("*.jpg") if p.is_file())
            existing_images.update(str(p) for p in d.glob("*.jpeg") if p.is_file())
            existing_images.update(str(p) for p in d.glob("*.webp") if p.is_file())

        result = subprocess.run(
            [gemini_cmd, "-p", full_prompt, "-y", "--sandbox", "--model", model],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(output_dir),
        )

        # 情况 1：目标文件已生成
        if output_path.exists() and output_path.stat().st_size > 1000:
            print(f"  ✅ 图片已生成: {output_path}")
            return output_path

        # 情况 2：Gemini 可能保存到了别的位置，查找新图片
        for d in [output_dir, Path.cwd()]:
            for pattern in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
                for f in sorted(d.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True):
                    if str(f) not in existing_images and f.stat().st_size > 1000:
                        shutil.move(str(f), str(output_path))
                        print(f"  ✅ 找到新生成图片，已移动到: {output_path}")
                        return output_path

        # 情况 3：CLI 输出中可能包含图片路径
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        full_output = stdout + stderr
        for line in full_output.split("\n"):
            line = line.strip()
            for ext in [".png", ".jpg", ".jpeg", ".webp"]:
                if ext in line:
                    # 尝试提取路径
                    import re
                    paths = re.findall(r'(/[^\s"\']+' + re.escape(ext) + r')', line)
                    for p in paths:
                        found = Path(p)
                        if found.exists() and found.stat().st_size > 1000:
                            shutil.copy2(str(found), str(output_path))
                            print(f"  ✅ 从输出中找到图片: {output_path}")
                            return output_path

        # 回退：生成占位图
        if not allow_placeholder:
            err_msg = (stderr or stdout or "Gemini CLI 未生成可用图片文件").strip()
            raise GeminiImageError(
                "Gemini CLI 未生成可用图片文件，已停止使用占位图回退"
                + (f": {err_msg}" if err_msg else "")
            )

        print(f"  ⚠️  Gemini CLI 未生成可用图片文件，使用占位图")
        if result.returncode != 0:
            print(f"  📝 CLI 返回码: {result.returncode}")
            err_msg = (stderr or stdout)[:200]
            if err_msg:
                print(f"  📝 错误信息: {err_msg}")

        _generate_placeholder(output_path, prompt)
        return output_path

    except subprocess.TimeoutExpired as exc:
        if allow_placeholder:
            print(f"  ⚠️  Gemini CLI 超时 ({timeout}s)，使用占位图")
            _generate_placeholder(output_path, prompt)
            return output_path
        raise GeminiImageError(f"Gemini CLI 超时 ({timeout}s)") from exc
    except FileNotFoundError as exc:
        if allow_placeholder:
            print(f"  ⚠️  Gemini CLI 未找到 ({gemini_cmd})，使用占位图")
            _generate_placeholder(output_path, prompt)
            return output_path
        raise GeminiImageError(f"Gemini CLI 未找到 ({gemini_cmd})") from exc


def _generate_placeholder(path: Path, prompt: str) -> None:
    """生成占位封面图（深色渐变背景 + 提示词摘要）。"""
    try:
        from PIL import Image, ImageDraw, ImageFont

        width, height = 1080, 1440
        img = Image.new("RGB", (width, height), color=(30, 30, 50))
        draw = ImageDraw.Draw(img)

        # 渐变背景
        for y in range(height):
            r = int(30 + (y / height) * 40)
            g = int(30 + (y / height) * 20)
            b = int(50 + (y / height) * 60)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # 装饰框
        draw.rectangle((24, 24, width - 24, height - 24), outline=(255, 140, 72), width=3)
        draw.rectangle((32, 32, width - 32, height - 32), outline=(255, 200, 100), width=1)

        # 加载字体
        font_candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
        ]
        font_large = font_small = None
        for fc in font_candidates:
            if Path(fc).exists():
                try:
                    font_large = ImageFont.truetype(fc, 52)
                    font_small = ImageFont.truetype(fc, 28)
                    break
                except OSError:
                    continue
        if font_large is None:
            font_large = ImageFont.load_default()
            font_small = font_large

        # 内容
        draw.text((60, 80), "🎨 AI 生成封面", fill=(255, 200, 100), font=font_large)
        draw.text((60, 160), "（占位图 — 等待真实生图接入）", fill=(180, 180, 200), font=font_small)

        # 分割线
        draw.line([(60, 220), (width - 60, 220)], fill=(100, 100, 120), width=1)

        # 提示词摘要
        y_offset = 250
        words = prompt[:300]
        for i in range(0, len(words), 22):
            line = words[i: i + 22]
            draw.text((60, y_offset), line, fill=(150, 150, 170), font=font_small)
            y_offset += 38
            if y_offset > 600:
                break

        # 底部标记
        draw.text(
            (60, height - 80),
            f"edu-media-openclaw • {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            fill=(100, 100, 120),
            font=font_small,
        )

        img.save(str(path))
    except ImportError:
        # 无 Pillow 时生成最小 PNG
        path.write_bytes(_minimal_png())


def _minimal_png() -> bytes:
    """生成最小 1x1 PNG。"""
    import struct
    import zlib

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + chunk(b"IEND", b"")


# ── CLI 入口 ──────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Gemini CLI 生图")
    parser.add_argument("--prompt", type=str, help="生图提示词")
    parser.add_argument("--output", type=str, help="输出路径")
    parser.add_argument("--test", action="store_true", help="运行自测")
    parser.add_argument("--dry-run", action="store_true", help="仅生成占位图")
    args = parser.parse_args()

    if args.test:
        test_prompt = "创作一张手绘风格的教育主题信息图，3:4 竖版，背景米色。"
        out = Path("/tmp/gemini_images/selftest.png")
        ensure_dir(out.parent)
        if args.dry_run:
            _generate_placeholder(out, test_prompt)
            print(f"✅ 占位图: {out}")
        else:
            result = generate_image(test_prompt, out)
            print(f"✅ 结果: {result}")
    elif args.prompt:
        result = generate_image(args.prompt, args.output)
        print(f"✅ 输出: {result}")
    else:
        parser.print_help()
