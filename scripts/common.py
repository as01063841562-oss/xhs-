#!/usr/bin/env python3
"""项目级通用工具。"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
CLIENTS_DIR = ROOT_DIR / "clients"
CONFIG_DIR = ROOT_DIR / "config"
DOCS_DIR = ROOT_DIR / "docs"
LOGS_DIR = ROOT_DIR / "logs"
OUTPUT_DIR = ROOT_DIR / "output"
OPENCLAW_DIR = Path.home() / ".openclaw"
OPENCLAW_CONFIG_PATH = OPENCLAW_DIR / "openclaw.json"

PLACEHOLDER_MARKERS = {
    "",
    "placeholder",
    "your_app_secret",
    "wx_your_app_id",
    "sk-your-api-key",
    "sk-your-text-api-key",
    "sk-your-image-api-key",
    "your-api-key",
    "你的笔名",
}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_client_root(client_slug: str) -> Path:
    return CLIENTS_DIR / client_slug


def get_client_workflow_path(client_slug: str) -> Path:
    return get_client_root(client_slug) / "config" / "workflow.yaml"


def get_client_state_dir(client_slug: str) -> Path:
    return ensure_dir(get_client_root(client_slug) / "state" / "feishu_dm")


def get_client_session_dir(client_slug: str) -> Path:
    return ensure_dir(get_client_root(client_slug) / "output" / "sessions")


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle) or {}


def _strip_json5_comments(text: str) -> str:
    result: list[str] = []
    in_string = False
    quote = ""
    escape = False
    index = 0
    length = len(text)

    while index < length:
        char = text[index]
        nxt = text[index + 1] if index + 1 < length else ""

        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                in_string = False
                quote = ""
            index += 1
            continue

        if char in {'"', "'"}:
            in_string = True
            quote = char
            result.append(char)
            index += 1
            continue

        if char == "/" and nxt == "/":
            index += 2
            while index < length and text[index] not in "\r\n":
                index += 1
            continue

        if char == "/" and nxt == "*":
            index += 2
            while index + 1 < length and not (text[index] == "*" and text[index + 1] == "/"):
                index += 1
            index += 2
            continue

        result.append(char)
        index += 1

    return "".join(result)


def _quote_json5_keys(text: str) -> str:
    pattern = re.compile(r'(^|[{,]\s*)([A-Za-z_$][A-Za-z0-9_$-]*)\s*:', re.MULTILINE)
    return pattern.sub(lambda match: f'{match.group(1)}"{match.group(2)}":', text)


def _remove_json5_trailing_commas(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _load_json5_like_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    cleaned = _remove_json5_trailing_commas(_quote_json5_keys(_strip_json5_comments(text)))
    return json.loads(cleaned or "{}") or {}


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            data[key] = value
    return data


def _resolve_secret_refs(value: Any, env_map: dict[str, str]) -> Any:
    if isinstance(value, dict):
        if value.get("source") == "env" and "id" in value:
            env_key = str(value.get("id") or "").strip()
            if not env_key:
                return None
            return env_map.get(env_key) or os.environ.get(env_key)
        return {key: _resolve_secret_refs(item, env_map) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_secret_refs(item, env_map) for item in value]
    return value


def _load_openclaw_config_tree(path: Path, root_dir: Path, env_map: dict[str, str]) -> dict[str, Any]:
    loaded = _load_json5_like_file(path)
    if not isinstance(loaded, dict):
        return {}

    include_items = loaded.get("$include")
    merged: dict[str, Any] = {}
    if isinstance(include_items, list):
        for include_item in include_items:
            include_path = (root_dir / str(include_item)).resolve()
            merged = deep_merge(merged, _load_openclaw_config_tree(include_path, root_dir, env_map))

    remaining = {key: value for key, value in loaded.items() if key != "$include"}
    merged = deep_merge(merged, remaining)
    return _resolve_secret_refs(merged, env_map) or {}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def resolve_path(path_str: str | None) -> Path | None:
    if not path_str:
        return None
    return Path(os.path.expanduser(path_str)).resolve()


def command_exists(command: str | None) -> bool:
    if not command:
        return False
    expanded = os.path.expanduser(command)
    if os.path.isabs(expanded):
        return os.path.isfile(expanded) and os.access(expanded, os.X_OK)
    return shutil.which(command) is not None


def _provider_api_key(block: dict[str, Any] | None) -> str | None:
    if not isinstance(block, dict):
        return None
    value = _pick_non_placeholder(block, ("api_key", "apiKey"))
    return str(value) if value else None


def _strip_model_provider(model_name: Any) -> str | None:
    if is_placeholder(model_name):
        return None
    text = str(model_name or "").strip()
    if not text:
        return None
    return text.split("/", 1)[-1]


def resolve_llm_api_config(
    llm_api_config: dict[str, Any] | None = None,
    openclaw_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve openai-compatible LLM settings from project + OpenClaw config."""

    resolved = dict(llm_api_config or {})
    backend = str(resolved.get("backend") or "openai_compatible")
    if backend != "openai_compatible":
        return resolved

    openclaw_data = openclaw_config if openclaw_config is not None else load_openclaw_config()
    providers = (
        openclaw_data.get("models", {}).get("providers", {})
        if isinstance(openclaw_data, dict)
        else {}
    )
    default_model = (
        openclaw_data.get("agents", {})
        .get("defaults", {})
        .get("model", {})
        .get("primary")
        if isinstance(openclaw_data, dict)
        else None
    )
    default_provider = ""
    if isinstance(default_model, str) and "/" in default_model:
        default_provider = default_model.split("/", 1)[0].strip()

    if config_state(resolved.get("base_url")) != "ready":
        openai_base_url = _pick_non_placeholder(
            providers.get("openai", {}) if isinstance(providers, dict) else {},
            ("base_url", "baseUrl"),
        )
        if openai_base_url:
            resolved["base_url"] = str(openai_base_url)

    if config_state(resolved.get("model")) != "ready":
        stripped_model = _strip_model_provider(default_model)
        if stripped_model:
            resolved["model"] = stripped_model

    if config_state(resolved.get("api_key")) != "ready":
        provider_order: list[str] = ["openai"]
        if default_provider and default_provider not in provider_order:
            provider_order.append(default_provider)
        for fallback_name in ("anthropic", "google"):
            if fallback_name not in provider_order:
                provider_order.append(fallback_name)

        for provider_name in provider_order:
            candidate = _provider_api_key(
                providers.get(provider_name, {}) if isinstance(providers, dict) else {}
            )
            if candidate:
                resolved["api_key"] = candidate
                break

    return resolved


def load_config(config_path: str | None = None) -> dict[str, Any]:
    path = resolve_path(config_path) if config_path else CONFIG_DIR / "config.yaml"
    if not path or not path.exists():
        raise FileNotFoundError(
            f"配置文件不存在: {path}. 请先检查 {CONFIG_DIR / 'config.yaml'}"
        )

    current = load_yaml_file(path)
    inherited_path = resolve_path(
        current.get("inherit", {}).get("wechat_config_path")
    )
    inherited = load_yaml_file(inherited_path) if inherited_path else {}
    merged = deep_merge(inherited, current)

    project = merged.setdefault("project", {})
    project.setdefault("name", "edu-media-openclaw")
    project.setdefault("log_dir", "./logs")
    project.setdefault("output_dir", "./output")
    project.setdefault("default_author", "AI 内容实验室")
    merged["llm_api"] = resolve_llm_api_config(
        merged.get("llm_api") or {},
        load_openclaw_config(),
    )
    return merged


def load_openclaw_config(config_path: str | None = None) -> dict[str, Any]:
    path = resolve_path(config_path) if config_path else OPENCLAW_CONFIG_PATH
    if not path or not path.exists():
        return {}
    root_dir = path.parent
    env_map = _load_env_file(root_dir / ".env")
    return _load_openclaw_config_tree(path, root_dir, env_map)


def _pick_non_placeholder(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key not in mapping:
            continue
        value = mapping.get(key)
        if not is_placeholder(value):
            return value
    return None


def _resolve_feishu_credentials_from_block(
    block: dict[str, Any],
    source_label: str,
) -> dict[str, Any] | None:
    if not isinstance(block, dict):
        return None

    app_id = _pick_non_placeholder(block, ("app_id", "appId"))
    app_secret = _pick_non_placeholder(block, ("app_secret", "appSecret"))
    if app_id and app_secret:
        return {
            "app_id": str(app_id),
            "app_secret": str(app_secret),
            "source": source_label,
        }

    accounts = block.get("accounts")
    if isinstance(accounts, dict) and accounts:
        preferred_names = [
            os.environ.get("OPENCLAW_FEISHU_ACCOUNT", "").strip(),
            str(block.get("account") or "").strip(),
            str(block.get("account_name") or "").strip(),
            str(block.get("defaultAccount") or "").strip(),
            "xiaohongshu-bot",
        ]
        tried: set[str] = set()
        for preferred in preferred_names:
            if not preferred or preferred in tried or preferred not in accounts:
                continue
            tried.add(preferred)
            resolved = _resolve_feishu_credentials_from_block(
                accounts.get(preferred) or {},
                f"{source_label}:accounts.{preferred}",
            )
            if resolved:
                return resolved

        for name, candidate in accounts.items():
            if name in tried:
                continue
            resolved = _resolve_feishu_credentials_from_block(
                candidate or {},
                f"{source_label}:accounts.{name}",
            )
            if resolved:
                return resolved
    return None


def resolve_feishu_credentials(
    feishu_config: dict[str, Any] | None = None,
    openclaw_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve Feishu app credentials from project config and OpenClaw config.

    OpenClaw config is the primary source. Project config can still act as a
    fallback for temporary local overrides, but we prefer keeping secrets in
    ~/.openclaw/openclaw.json to match the reference workflow.
    """

    feishu_config = feishu_config or {}
    openclaw_data = openclaw_config if openclaw_config is not None else load_openclaw_config()
    openclaw_feishu = (
        openclaw_data.get("channels", {}).get("feishu", {})
        if isinstance(openclaw_data, dict)
        else {}
    )
    resolved = _resolve_feishu_credentials_from_block(
        openclaw_feishu if isinstance(openclaw_feishu, dict) else {},
        "~/.openclaw/openclaw.json",
    )
    if resolved:
        return resolved

    project_resolved = _resolve_feishu_credentials_from_block(
        feishu_config,
        "config.yaml",
    )
    if project_resolved:
        return project_resolved

    return {
        "app_id": None,
        "app_secret": None,
        "source": "missing",
    }


def save_yaml_file(path: Path, data: Any) -> Path:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            data,
            handle,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    return path


def save_json_file(path: Path, data: Any) -> Path:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return path


def save_text_file(path: Path, text: str) -> Path:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def slugify(text: str, limit: int = 36) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned[:limit] or "task"


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def make_run_dir(platform: str, topic: str) -> Path:
    path = OUTPUT_DIR / platform / f"{timestamp()}-{slugify(topic)}"
    return ensure_dir(path)


def is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        candidate = value.strip()
        return candidate in PLACEHOLDER_MARKERS or candidate.startswith("sk-your-")
    return False


def config_state(value: Any) -> str:
    if value is None or value == "":
        return "missing"
    if is_placeholder(value):
        return "placeholder"
    return "ready"


def normalize_openai_base_url(base_url: str, endpoint: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/{endpoint.lstrip('/')}"
    return f"{normalized}/v1/{endpoint.lstrip('/')}"


def mask_secret(value: str | None) -> str:
    if not value:
        return "missing"
    if is_placeholder(value):
        return "placeholder"
    if len(value) <= 8:
        return "set"
    return f"{value[:4]}...{value[-4:]}"


def markdown_table(rows: list[tuple[str, str]]) -> str:
    header = "| 项 | 状态 |\n| --- | --- |\n"
    body = "\n".join(f"| {left} | {right} |" for left, right in rows)
    return header + body + "\n"
