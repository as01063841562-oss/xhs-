#!/usr/bin/env python3
"""检查首期工程的环境、依赖和配置状态。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

from common import (
    CONFIG_DIR,
    DOCS_DIR,
    LOGS_DIR,
    command_exists,
    config_state,
    ensure_dir,
    load_config,
    resolve_feishu_credentials,
    markdown_table,
    mask_secret,
    resolve_path,
    save_json_file,
    save_text_file,
    timestamp,
)
from gemini_web_image import browser_image_ready


def module_state(module_name: str) -> str:
    return "ready" if importlib.util.find_spec(module_name) else "missing"


def command_state(command: str) -> str:
    return "ready" if command_exists(command) else "missing"


def safe_command_output(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return (completed.stdout or completed.stderr).strip()
    except Exception as exc:  # pragma: no cover - defensive
        return f"error: {exc}"


def collect_report() -> dict:
    config = load_config()
    feishu_cfg = config.get("feishu", {})
    resolved_feishu = resolve_feishu_credentials(feishu_cfg)
    inherited_path = (
        config.get("inherit", {}).get("wechat_config_path")
        or "not-configured"
    )
    llm_backend = config.get("llm_api", {}).get("backend", "openai_compatible")
    image_backend = config.get("image_api", {}).get("backend", "openai_compatible")
    gemini_image_backend = config.get("gemini_image", {}).get("backend", "gemini_cli")
    gemini_image_command = config.get("gemini_image", {}).get("command", "/opt/homebrew/bin/gemini")
    llm_cli_config_path = Path.home() / ".config" / "gemini" / "config.json"
    llm_cli_command = config.get("llm_cli", {}).get("command", "/opt/homebrew/bin/node")
    llm_cli_script = config.get("llm_cli", {}).get("script_path", "/Users/lmsx/gemini-cli.js")
    image_cli_command = config.get("image_cli", {}).get("command", "/Users/lmsx/.local/bin/uv")
    image_cli_script = config.get(
        "image_cli", {}
    ).get(
        "script_path",
        "/Users/lmsx/.local/node/lib/node_modules/openclaw/skills/nano-banana-pro/scripts/generate_image.py",
    )
    image_cli_api_key = config.get("image_cli", {}).get("api_key") or os.environ.get(
        "GEMINI_API_KEY", ""
    )
    browser_settings = config.get("browser_image", {})
    browser_profile_dir = resolve_path(browser_settings.get("profile_dir"))
    browser_source_profile_dir = resolve_path(browser_settings.get("source_profile_dir"))
    browser_launcher = browser_settings.get("launcher", "open")
    browser_profile_ready = bool(
        browser_profile_dir
        and browser_profile_dir.exists()
        and browser_profile_dir.is_dir()
        and any(browser_profile_dir.iterdir())
    )
    browser_source_profile_ready = bool(
        browser_source_profile_dir
        and browser_source_profile_dir.exists()
        and browser_source_profile_dir.is_dir()
        and any(browser_source_profile_dir.iterdir())
    )
    feishu_receive_id = feishu_cfg.get("receive_id") or feishu_cfg.get("receiveId")
    feishu_receive_id_type = feishu_cfg.get("receive_id_type") or feishu_cfg.get("receiveIdType") or "open_id"

    if gemini_image_backend == "gemini_cli":
        gemini_image_ready = command_state(gemini_image_command)
    elif gemini_image_backend == "gemini_web":
        gemini_image_ready = "ready" if browser_image_ready(browser_settings) else "missing"
    else:
        gemini_image_ready = "missing"

    report = {
        "timestamp": timestamp(),
        "project_root": str(CONFIG_DIR.parent),
        "commands": {
            "openclaw": command_state("openclaw"),
            "python3": command_state("python3"),
        },
        "python_modules": {
            "requests": module_state("requests"),
            "yaml": module_state("yaml"),
            "PIL": module_state("PIL"),
            "playwright": module_state("playwright"),
        },
        "config": {
            "llm_backend": llm_backend,
            "image_backend": image_backend,
            "gemini_image_backend": gemini_image_backend,
            "gemini_image_command": gemini_image_command,
            "gemini_image_ready": gemini_image_ready,
            "browser_image_ready": "ready" if browser_image_ready(browser_settings) else "missing",
            "browser_launcher": command_state(browser_launcher) if browser_launcher != "open" else "ready",
            "browser_profile_dir": str(browser_profile_dir) if browser_profile_dir else "missing",
            "browser_profile_dir_exists": browser_profile_ready,
            "browser_source_profile_dir": str(browser_source_profile_dir) if browser_source_profile_dir else "missing",
            "browser_source_profile_dir_exists": browser_source_profile_ready,
            "wechat_app_id": config_state(config.get("wechat", {}).get("app_id")),
            "wechat_app_secret": config_state(
                config.get("wechat", {}).get("app_secret")
            ),
            "feishu_app_id": config_state(resolved_feishu.get("app_id")),
            "feishu_app_secret": config_state(resolved_feishu.get("app_secret")),
            "feishu_credentials_source": resolved_feishu.get("source", "missing"),
            "feishu_receive_id": config_state(feishu_receive_id),
            "feishu_receive_id_type": feishu_receive_id_type,
            "llm_api_key": config_state(config.get("llm_api", {}).get("api_key")),
            "image_api_key": config_state(config.get("image_api", {}).get("api_key")),
            "llm_model": config_state(config.get("llm_api", {}).get("model")),
            "image_model": config_state(config.get("image_api", {}).get("model")),
            "llm_cli_command": command_state(llm_cli_command),
            "llm_cli_script": "ready" if Path(llm_cli_script).exists() else "missing",
            "llm_cli_api_key": config_state(config.get("llm_cli", {}).get("api_key")),
            "llm_cli_user_config": "ready" if llm_cli_config_path.exists() else "missing",
            "image_cli_command": command_state(image_cli_command),
            "image_cli_script": "ready" if Path(image_cli_script).exists() else "missing",
            "image_cli_api_key": config_state(image_cli_api_key),
            "inherit_wechat_config_path": inherited_path,
            "inherit_wechat_config_exists": Path(inherited_path).exists()
            if inherited_path != "not-configured"
            else False,
        },
        "sanitized": {
            "llm_api_key": mask_secret(config.get("llm_api", {}).get("api_key")),
            "image_api_key": mask_secret(config.get("image_api", {}).get("api_key")),
            "llm_cli_api_key": mask_secret(config.get("llm_cli", {}).get("api_key")),
            "image_cli_api_key": mask_secret(image_cli_api_key),
        },
        "openclaw": {
            "status": safe_command_output(["openclaw", "status"]),
            "health": safe_command_output(["openclaw", "health"]),
        },
    }
    return report


def render_markdown(report: dict) -> str:
    rows = [
        ("openclaw 命令", report["commands"]["openclaw"]),
        ("python3 命令", report["commands"]["python3"]),
        ("requests", report["python_modules"]["requests"]),
        ("PyYAML", report["python_modules"]["yaml"]),
        ("Pillow", report["python_modules"]["PIL"]),
        ("playwright", report["python_modules"]["playwright"]),
        ("文本后端", report["config"]["llm_backend"]),
        ("图片后端", report["config"]["image_backend"]),
        ("Gemini 生图后端", report["config"]["gemini_image_backend"]),
        ("Gemini 生图命令", report["config"]["gemini_image_command"]),
        ("Gemini 生图就绪", report["config"]["gemini_image_ready"]),
        ("浏览器生图", report["config"]["browser_image_ready"]),
        ("浏览器 profile", "ready" if report["config"]["browser_profile_dir_exists"] else "missing"),
        ("公众号 AppID", report["config"]["wechat_app_id"]),
        ("公众号 AppSecret", report["config"]["wechat_app_secret"]),
        ("飞书 AppID", report["config"]["feishu_app_id"]),
        ("飞书 AppSecret", report["config"]["feishu_app_secret"]),
        ("飞书凭证来源", report["config"]["feishu_credentials_source"]),
        ("飞书 receive_id", report["config"]["feishu_receive_id"]),
        ("飞书 receive_id_type", report["config"]["feishu_receive_id_type"]),
        ("文本模型 API Key", report["config"]["llm_api_key"]),
        ("图片模型 API Key", report["config"]["image_api_key"]),
        ("文本模型", report["config"]["llm_model"]),
        ("图片模型", report["config"]["image_model"]),
        ("Gemini CLI 命令", report["config"]["llm_cli_command"]),
        ("Gemini CLI 脚本", report["config"]["llm_cli_script"]),
        ("Gemini CLI Key", report["config"]["llm_cli_api_key"]),
        ("Gemini CLI 用户配置", report["config"]["llm_cli_user_config"]),
        ("Nano Banana 命令", report["config"]["image_cli_command"]),
        ("Nano Banana 脚本", report["config"]["image_cli_script"]),
        ("Nano Banana Key", report["config"]["image_cli_api_key"]),
        (
            "继承公众号配置",
            "ready" if report["config"]["inherit_wechat_config_exists"] else "missing",
        ),
    ]
    status_excerpt = "\n".join(report["openclaw"]["status"].splitlines()[:12])
    health_excerpt = "\n".join(report["openclaw"]["health"].splitlines()[:8])
    return (
        "# 环境基线\n\n"
        f"- 生成时间：`{report['timestamp']}`\n"
        f"- 项目目录：`{report['project_root']}`\n\n"
        + markdown_table(rows)
        + "\n## OpenClaw status 摘要\n\n```text\n"
        + status_excerpt
        + "\n```\n\n## OpenClaw health 摘要\n\n```text\n"
        + health_excerpt
        + "\n```\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="检查环境与配置状态")
    parser.add_argument("--write", action="store_true", help="写入 docs/logs")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    report = collect_report()

    if args.write:
        ensure_dir(LOGS_DIR)
        ensure_dir(DOCS_DIR)
        save_json_file(LOGS_DIR / f"baseline-{report['timestamp']}.json", report)
        save_json_file(LOGS_DIR / "baseline-latest.json", report)
        save_text_file(DOCS_DIR / "environment_baseline.md", render_markdown(report))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(render_markdown(report))


if __name__ == "__main__":
    main()
