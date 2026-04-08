#!/usr/bin/env python3
"""Gemini 网页端生图后端。

这个模块负责把本机 Chrome + Gemini 网页页面串起来，完成：
1. 打开/复用带登录态的 Chrome profile
2. 切到 Gemini 的图片生成模式
3. 输入提示词并等待结果
4. 通过“复制图片”或“下载原图”把结果保存到本地
5. 归一化为目标尺寸 PNG
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from common import ensure_dir, resolve_path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_DIR = ROOT_DIR / ".runtime" / "chrome-user-profile"
DEFAULT_SOURCE_PROFILE_DIR = Path.home() / "Library/Application Support/Google/Chrome"
DEFAULT_REMOTE_DEBUG_PORT = 9227
DEFAULT_GEMINI_URL = "https://gemini.google.com/app"
DEFAULT_CHROME_APP = "Google Chrome"


class GeminiWebImageError(RuntimeError):
    """Gemini 网页生图失败。"""


def _settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    return dict(settings or {})


def _setting_path(settings: dict[str, Any], key: str, default: Path) -> Path:
    raw = settings.get(key)
    if raw:
        resolved = resolve_path(str(raw))
        if resolved:
            return resolved
    return default


def _setting_str(settings: dict[str, Any], key: str, default: str) -> str:
    value = settings.get(key)
    return default if value in {None, ""} else str(value)


def _setting_int(settings: dict[str, Any], key: str, default: int) -> int:
    value = settings.get(key)
    try:
        return default if value in {None, ""} else int(value)
    except (TypeError, ValueError):
        return default


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _dir_has_content(path: Path) -> bool:
    try:
        return path.exists() and path.is_dir() and any(path.iterdir())
    except Exception:
        return False


def browser_image_ready(settings: dict[str, Any] | None = None) -> bool:
    """检查 Gemini 网页生图后端是否具备最低可运行条件。"""
    cfg = _settings(settings)

    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False

    launcher = _setting_str(cfg, "launcher", "open")
    if launcher != "open" and shutil.which(launcher) is None and not Path(launcher).exists():
        return False

    profile_dir = _setting_path(cfg, "profile_dir", DEFAULT_PROFILE_DIR)
    source_profile_dir = _setting_path(cfg, "source_profile_dir", DEFAULT_SOURCE_PROFILE_DIR)
    return _dir_has_content(profile_dir) or _dir_has_content(source_profile_dir)


def _ensure_profile_dir(settings: dict[str, Any]) -> Path:
    profile_dir = _setting_path(settings, "profile_dir", DEFAULT_PROFILE_DIR)
    source_profile_dir = _setting_path(settings, "source_profile_dir", DEFAULT_SOURCE_PROFILE_DIR)

    if profile_dir.exists() and any(profile_dir.iterdir()):
        return profile_dir

    ensure_dir(profile_dir.parent)
    if profile_dir.exists():
        shutil.rmtree(profile_dir)

    if source_profile_dir.exists():
        print(f"  📁 复制 Chrome 登录态: {source_profile_dir} -> {profile_dir}")
        shutil.copytree(source_profile_dir, profile_dir)
    else:
        print(f"  ⚠️  源 Chrome profile 不存在，创建空 profile: {profile_dir}")
        ensure_dir(profile_dir)
    return profile_dir


def _launch_chrome(settings: dict[str, Any], profile_dir: Path, port: int) -> None:
    if _port_open(port):
        return

    chrome_app = _setting_str(settings, "chrome_app", DEFAULT_CHROME_APP)
    gemini_url = _setting_str(settings, "gemini_url", DEFAULT_GEMINI_URL)
    launcher = _setting_str(settings, "launcher", "open")

    if launcher == "open":
        cmd = [
            launcher,
            "-na",
            chrome_app,
            "--args",
            f"--user-data-dir={profile_dir}",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            gemini_url,
        ]
    else:
        cmd = [
            launcher,
            f"--user-data-dir={profile_dir}",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            gemini_url,
        ]
    print(f"  🚀 启动 Chrome: {chrome_app} (port={port})")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_for_port(port: int, timeout: int) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        if _port_open(port):
            return
        try:
            import requests

            requests.get(f"http://127.0.0.1:{port}/json/version", timeout=1)
            return
        except Exception as exc:  # pragma: no cover - retry loop
            last_error = exc
            time.sleep(1)
    raise GeminiWebImageError(f"Chrome remote debugging 端口 {port} 未就绪: {last_error}")


def _wait_for_visible_button(page, names: list[str], timeout_ms: int):
    import re as _re

    candidates = []
    for name in names:
        candidates.append(page.get_by_role("button", name=name))
        candidates.append(page.get_by_role("button", name=_re.compile(name, _re.I)))
    deadline = time.time() + (timeout_ms / 1000)
    last_error: Exception | None = None
    while time.time() < deadline:
        for locator in candidates:
            try:
                if locator.count() > 0 and locator.first.is_visible():
                    return locator.first
            except Exception as exc:  # pragma: no cover - best effort
                last_error = exc
        time.sleep(1)
    raise GeminiWebImageError(f"等待按钮超时: {names}, last_error={last_error}")


def _result_generation_in_progress(page) -> bool:
    try:
        stop_button = page.get_by_role("button", name=re.compile(r"대답 생성 중지|Stop generating|停止生成", re.I))
        if stop_button.count() > 0 and stop_button.first.is_visible():
            return True
    except Exception:
        pass
    try:
        body_text = page.locator("body").inner_text()
    except Exception:
        return False
    return bool(re.search(r"Creating your image|Synthesizing Visual Elements|생성 중", body_text, re.I))


def _wait_for_image_result_ready(page, timeout_ms: int) -> None:
    deadline = time.time() + timeout_ms / 1000
    last_state = "unknown"
    while time.time() < deadline:
        if _result_generation_in_progress(page):
            last_state = "generating"
            page.wait_for_timeout(2_000)
            continue
        try:
            _wait_for_visible_button(
                page,
                ["이미지 복사", "Copy image", "원본 크기 이미지 다운로드", "Download original size image"],
                2_000,
            )
            return
        except Exception:
            last_state = "no-save-action"
            page.wait_for_timeout(2_000)
    raise GeminiWebImageError(f"等待 Gemini 图片结果超时: {last_state}")


def _first_clickable(page, locators, timeout_ms: int):
    last_error: Exception | None = None
    for locator in locators:
        try:
            target = locator.first if hasattr(locator, "first") else locator
            if target.count() == 0:
                continue
            if not target.is_visible():
                continue
            target.click(timeout=min(timeout_ms, 5_000), force=True)
            return target
        except Exception as exc:  # pragma: no cover - best effort
            last_error = exc
    raise GeminiWebImageError(f"未找到可点击元素: {last_error}")


def _save_clipboard_png(output_path: Path) -> None:
    if output_path.exists():
        output_path.unlink()
    script = [
        'try',
        'set theData to the clipboard as «class PNGf»',
        f'set fileName to POSIX file "{output_path}"',
        'set outFile to open for access fileName with write permission',
        'write theData to outFile',
        'close access outFile',
        'return "ok"',
        'on error errMsg',
        'return "error: " & errMsg',
        'end try',
    ]
    completed = subprocess.run(
        ["osascript", *sum([["-e", line] for line in script], [])],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    result = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode == 0 and output_path.exists():
        return

    try:
        completed = subprocess.run(
            ["pbpaste", "-Prefer", "png"],
            check=False,
            capture_output=True,
            timeout=20,
        )
        if completed.returncode == 0 and completed.stdout:
            output_path.write_bytes(completed.stdout)
            if output_path.exists() and output_path.stat().st_size > 1000:
                return
    except FileNotFoundError:
        pass

    raise GeminiWebImageError(f"保存剪贴板失败: {result}")


def _normalize_image(path: Path, target_size: tuple[int, int]) -> None:
    from PIL import Image, ImageOps

    image = Image.open(path).convert("RGB")
    if image.size != target_size:
        image = ImageOps.pad(
            image,
            target_size,
            method=Image.Resampling.LANCZOS,
            color=(255, 255, 255),
            centering=(0.5, 0.5),
        )
    image.save(path, "PNG", optimize=True)


def _save_placeholder(path: Path, prompt: str, size: tuple[int, int]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = size
    image = Image.new("RGB", (width, height), color=(247, 244, 236))
    draw = ImageDraw.Draw(image)
    draw.rectangle((32, 32, width - 32, height - 32), outline=(224, 152, 88), width=6)
    draw.rectangle((44, 44, width - 44, height - 44), outline=(180, 125, 68), width=2)

    def load_font(font_size: int):
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
                    return ImageFont.truetype(str(font_path), size=font_size)
                except OSError:
                    continue
        return ImageFont.load_default()

    title_font = load_font(56)
    body_font = load_font(26)

    draw.text((60, 70), "Gemini 网页生图占位图", fill=(102, 63, 24), font=title_font)
    draw.text((60, 150), f"{width}x{height}", fill=(140, 104, 68), font=body_font)

    wrapped = prompt[:320]
    y = 220
    for i in range(0, len(wrapped), 28):
        draw.text((60, y), wrapped[i:i + 28], fill=(92, 92, 92), font=body_font)
        y += 38
        if y > height - 120:
            break

    image.save(path, "PNG", optimize=True)


def _get_browser_page(browser, gemini_url: str):
    context = browser.contexts[0] if getattr(browser, "contexts", None) else None
    if context is None:
        context = browser.new_context()
    page = context.new_page()

    try:
        page.goto(gemini_url, wait_until="domcontentloaded", timeout=60_000)
    except Exception:
        pass
    return page


def _click_if_visible(page, locators, timeout_ms: int) -> bool:
    for locator in locators:
        try:
            target = locator.first if hasattr(locator, "first") else locator
            if target.count() == 0:
                continue
            if target.is_visible():
                target.click(timeout=timeout_ms)
                return True
        except Exception:
            continue
    return False


def _image_mode_active(page) -> bool:
    """判断 Gemini 网页是否已经切到图片生成模式。"""
    active_chip = page.get_by_role(
        "button",
        name=re.compile(r"이미지 만들기 선택 해제|Create image deselect", re.I),
    )
    try:
        return active_chip.count() > 0 and active_chip.first.is_visible()
    except Exception:
        return False


def _ensure_image_mode(page, timeout_ms: int) -> None:
    """打开工具抽屉并切换到图片生成模式。"""
    if _image_mode_active(page):
        return

    deadline = time.time() + timeout_ms / 1000
    last_error: Exception | None = None
    drawer_button = page.locator("button.toolbox-drawer-button-with-label").first
    while time.time() < deadline:
        try:
            if _image_mode_active(page):
                return

            if drawer_button.get_attribute("aria-expanded") != "true":
                drawer_button.click(timeout=timeout_ms, force=True)
                page.wait_for_timeout(500)

            mode_candidates = [
                page.get_by_role("menuitemcheckbox", name=re.compile(r"이미지 만들기|Create image", re.I)),
                page.get_by_role("button", name=re.compile(r"🖼️\s*이미지 만들기|이미지 만들기|Create image", re.I)),
                page.get_by_text(re.compile(r"🖼️\s*이미지 만들기|이미지 만들기|Create image", re.I)),
            ]
            _first_clickable(page, mode_candidates, timeout_ms)
            page.wait_for_timeout(1_000)
            if _image_mode_active(page):
                return
        except Exception as exc:  # pragma: no cover - best effort
            last_error = exc
        page.wait_for_timeout(1_000)
    raise GeminiWebImageError(f"无法切换到 Gemini 图片模式: {last_error}")


def _wait_for_image_prompt_box(page, timeout_ms: int):
    """等待图片模式的提示词输入框出现。"""
    deadline = time.time() + timeout_ms / 1000
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            candidates = [
                page.locator("textarea:visible"),
                page.locator('[role="textbox"]:visible'),
                page.locator('[contenteditable="true"]:visible'),
            ]
            for locator in candidates:
                if locator.count() == 0 or not locator.first.is_visible():
                    continue
                prompt_box = locator.first
                placeholder = (prompt_box.get_attribute("placeholder") or "").strip()
                aria_label = (prompt_box.get_attribute("aria-label") or "").strip()
                contenteditable = (prompt_box.get_attribute("contenteditable") or "").strip().lower()
                if placeholder and not re.search(r"Gemini에게 물어보기", placeholder, re.I):
                    return prompt_box
                if re.search(r"(이미지|Describe|Prompt|설명)", placeholder, re.I):
                    return prompt_box
                if re.search(r"(이미지|Describe|Prompt|설명)", aria_label, re.I):
                    return prompt_box
                if contenteditable == "true":
                    return prompt_box
        except Exception as exc:  # pragma: no cover - best effort
            last_error = exc
        time.sleep(0.5)
    raise GeminiWebImageError(f"找不到 Gemini 图片描述输入框: {last_error}")


def _style_picker_visible(page) -> bool:
    """判断 Gemini 是否仍停留在图片风格选择界面。"""
    try:
        body_text = page.locator("body").inner_text()
    except Exception:
        return False
    return "이미지에 어울리는 스타일을 고르세요" in body_text


def _ensure_image_style(page, timeout_ms: int, style_name: str = "천연색") -> None:
    """在图片模式下选择一个默认风格，触发提示词输入框出现。"""
    if not _style_picker_visible(page):
        return

    style_candidates = [
        page.get_by_role("button", name=re.compile(re.escape(style_name), re.I)),
        page.get_by_text(re.compile(re.escape(style_name), re.I)),
    ]
    _first_clickable(page, style_candidates, timeout_ms)
    page.wait_for_timeout(1_000)


def _send_prompt(page, prompt_box, timeout_ms: int = 15_000) -> bool:
    """把提示词发送给 Gemini。

    Gemini 网页的发送按钮会在输入后才显现，所以这里先等按钮变为可见，
    再优先直接点击；如果按钮仍然不可用，再退回键盘提交。
    """

    send_candidates = [
        page.get_by_role("button", name=re.compile(r"메시지 보내기|发送消息|发送|Send message|보내기|Send", re.I)),
        page.locator('button[aria-label="메시지 보내기"]'),
        page.locator('button[aria-label*="보내기"]'),
        page.locator('button[aria-label*="发送"]'),
        page.locator('button[aria-label*="Send"]'),
    ]

    deadline = time.time() + timeout_ms / 1000
    last_error: Exception | None = None
    while time.time() < deadline:
        for locator in send_candidates:
            try:
                target = locator.first if hasattr(locator, "first") else locator
                if target.count() == 0:
                    continue
                if target.is_visible() and not target.is_disabled():
                    target.click(timeout=5_000, force=True)
                    return True
            except Exception as exc:  # pragma: no cover - best effort
                last_error = exc
        time.sleep(0.3)

    try:
        prompt_box.click(timeout=5_000)
        page.keyboard.press("Meta+Enter")
        return True
    except Exception:
        try:
            prompt_box.click(timeout=5_000)
            page.keyboard.press("Control+Enter")
            return True
        except Exception as exc:  # pragma: no cover - best effort
            last_error = exc
    raise GeminiWebImageError(f"无法发送 Gemini 提示词: {last_error}")


def render_gemini_web_image(
    prompt: str,
    output_path: str | Path,
    size: tuple[int, int],
    settings: dict[str, Any] | None = None,
) -> Path:
    """通过 Gemini 网页生成图片并保存到指定路径。"""
    cfg = _settings(settings)
    output_path = Path(output_path)
    ensure_dir(output_path.parent)

    profile_dir = _ensure_profile_dir(cfg)
    port = _setting_int(cfg, "remote_debug_port", DEFAULT_REMOTE_DEBUG_PORT)
    launch_timeout = _setting_int(cfg, "launch_timeout", 90)
    page_timeout = _setting_int(cfg, "page_timeout", 180)
    gemini_url = _setting_str(cfg, "gemini_url", DEFAULT_GEMINI_URL)

    if not _port_open(port):
        _launch_chrome(cfg, profile_dir, port)
        _wait_for_port(port, launch_timeout)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - dependency issue
        raise GeminiWebImageError(f"Playwright 未安装: {exc}") from exc

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        page = _get_browser_page(browser, gemini_url)

        _ensure_image_mode(page, page_timeout * 1000)
        _ensure_image_style(page, page_timeout * 1000)
        prompt_box = _wait_for_image_prompt_box(page, page_timeout * 1000)

        prompt_box.fill(prompt)
        page.wait_for_timeout(800)
        _send_prompt(page, prompt_box)
        _wait_for_image_result_ready(page, page_timeout * 1000)

        copy_button = _wait_for_visible_button(
            page,
            ["이미지 복사", "复制图片", "Copy image", "이미지 공유"],
            10_000,
        )
        try:
            copy_button.click(timeout=10_000, force=True)
            time.sleep(1.5)
            _save_clipboard_png(output_path)
            _normalize_image(output_path, size)
            return output_path
        except Exception as exc:
            print(f"  ⚠️  剪贴板保存失败，尝试原图下载: {exc}")

        download_button = _wait_for_visible_button(
            page,
            ["원본 크기 이미지 다운로드", "下载原始尺寸图片", "下载原图", "Download original size image", "원본 크기"],
            10_000,
        )
        try:
            with page.expect_download(timeout=20_000) as download_info:
                download_button.click(timeout=10_000, force=True)
            download = download_info.value
            download.save_as(str(output_path))
            _normalize_image(output_path, size)
            return output_path
        except Exception as exc:
            print(f"  ⚠️  原图下载失败，尝试再次下载原图: {exc}")

        download_candidates = [
            page.get_by_role("button", name=re.compile(r"원본 크기 이미지 다운로드|다운로드|下载原始尺寸图片|下载原图|Download original size image|원본 크기", re.I)),
            page.get_by_text(re.compile(r"원본 크기 이미지 다운로드|다운로드|下载原始尺寸图片|下载原图|Download original size image|원본 크기", re.I)),
        ]
        for locator in download_candidates:
            try:
                target = locator.first if hasattr(locator, "first") else locator
                if target.count() == 0 or not target.is_visible():
                    continue
                with page.expect_download(timeout=20_000) as download_info:
                    target.click(timeout=10_000, force=True)
                download = download_info.value
                download.save_as(str(output_path))
                _normalize_image(output_path, size)
                return output_path
            except Exception:
                continue

        raise GeminiWebImageError("Gemini 网页端没有产出可保存的图片")

    # 不会走到这里，保留给类型检查器
    return output_path


def generate_placeholder_image(path: str | Path, prompt: str, size: tuple[int, int]) -> Path:
    path = Path(path)
    ensure_dir(path.parent)
    try:
        _save_placeholder(path, prompt, size)
    except Exception:
        path.write_bytes(_minimal_png())
    return path


def _minimal_png() -> bytes:
    import struct
    import zlib

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + chunk(b"IEND", b"")
