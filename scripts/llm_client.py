#!/usr/bin/env python3
"""文本模型客户端，支持 OpenAI 兼容接口和本地 CLI 后端。"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import requests

from common import command_exists, config_state, is_placeholder, normalize_openai_base_url


class LLMConfigError(RuntimeError):
    """Raised when the LLM client is not configured."""


class LLMResponseError(RuntimeError):
    """Raised when the LLM response is malformed."""


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if fence_match:
        return json.loads(fence_match.group(1))

    loose_match = re.search(r"(\{.*\})", text, re.S)
    if loose_match:
        return json.loads(loose_match.group(1))

    raise LLMResponseError("模型返回中未找到可解析的 JSON 对象。")


def decode_json_response(response: requests.Response) -> dict[str, Any]:
    """Decode provider responses robustly even when headers lie about charset."""

    try:
        return json.loads(response.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return response.json()


class ProjectLLM:
    def __init__(self, root_config: dict[str, Any]):
        self.root_config = root_config
        self.api_config = root_config.get("llm_api", {})
        self.cli_config = root_config.get("llm_cli", {})
        self.backend = self.api_config.get("backend", "openai_compatible")

    @property
    def ready(self) -> bool:
        if self.backend == "gemini_cli":
            cmd = self.cli_config.get("command", "/opt/homebrew/bin/gemini")
            return command_exists(cmd)

        if self.backend == "gemini_local_cli":
            script_ready = Path(
                self.cli_config.get("script_path", "/Users/lmsx/gemini-cli.js")
            ).exists()
            command_ready = command_exists(
                self.cli_config.get("command", "/opt/homebrew/bin/node")
            )
            key_ready = (
                config_state(self.cli_config.get("api_key")) == "ready"
                or self._gemini_local_config_has_key()
            )
            return script_ready and command_ready and key_ready

        api_key = self.api_config.get("api_key")
        model = self.api_config.get("model")
        return (
            config_state(api_key) == "ready"
            and config_state(model) == "ready"
            and not is_placeholder(self.api_config.get("base_url"))
        )

    def require_ready(self) -> None:
        if self.ready:
            return
        if self.backend == "gemini_cli":
            raise LLMConfigError(
                "gemini CLI 未找到。请确认 /opt/homebrew/bin/gemini 存在，"
                "或通过 brew install gemini-cli 安装。"
            )
        if self.backend == "gemini_local_cli":
            raise LLMConfigError(
                "llm_cli 未配置完成。请检查 config/config.yaml 中的 llm_api.backend、"
                "llm_cli.command、llm_cli.script_path，以及 llm_cli.api_key 或 ~/.config/gemini/config.json。"
            )
        raise LLMConfigError(
            "llm_api 未配置完成，请检查 config/config.yaml 中的 base_url、api_key、model。"
        )

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        expect_json: bool = False,
    ) -> str:
        self.require_ready()
        if self.backend == "gemini_cli":
            return self._chat_via_gemini_cli_native(
                system_prompt,
                user_prompt,
                expect_json=expect_json,
            )
        if self.backend == "gemini_local_cli":
            return self._chat_via_gemini_cli(
                system_prompt,
                user_prompt,
                expect_json=expect_json,
            )
        return self._chat_via_openai_compatible(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            expect_json=expect_json,
        )

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        content = self.chat(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            expect_json=True,
        )
        return extract_json_object(content)

    def _chat_via_openai_compatible(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        expect_json: bool = False,
    ) -> str:
        url = normalize_openai_base_url(
            self.api_config.get("base_url", "https://api.openai.com"),
            "chat/completions",
        )
        headers = {
            "Authorization": f"Bearer {self.api_config['api_key']}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.api_config["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": (
                self.api_config.get("temperature", 0.8)
                if temperature is None
                else temperature
            ),
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if expect_json:
            payload["response_format"] = {"type": "json_object"}

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.api_config.get("timeout", 120),
        )
        response.raise_for_status()
        data = decode_json_response(response)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMResponseError(f"模型返回格式异常: {data}") from exc

    def _chat_via_gemini_cli_native(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        expect_json: bool = False,
    ) -> str:
        """通过 Gemini CLI (/opt/homebrew/bin/gemini) 调用。"""
        command = self.cli_config.get("command", "/opt/homebrew/bin/gemini")
        model = self.cli_config.get("model", "gemini-2.5-flash")

        prompt = (
            f"[系统指令]\n{system_prompt}\n\n"
            f"[用户请求]\n{user_prompt}"
        )
        if expect_json:
            prompt += "\n\n[输出要求] 请只输出一个合法的 JSON 对象，不要输出任何其他文字、解释或 markdown 代码块标记。"

        timeout = self.cli_config.get("timeout", self.api_config.get("timeout", 120))
        cmd_args = [command, "-p", prompt, "--model", model]
        completed = subprocess.run(
            cmd_args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        # Gemini CLI 有时 returncode!=0 但 stdout 有有效输出（keychain 警告导致）
        stdout = completed.stdout.strip()
        if stdout:
            return stdout
        if completed.returncode != 0:
            error_text = (completed.stderr or "").strip()
            raise LLMResponseError(f"Gemini CLI 调用失败: {error_text}")
        return stdout

    def _chat_via_gemini_cli(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        expect_json: bool = False,
    ) -> str:
        """通过旧版 node gemini-cli.js 调用（保留兼容）。"""
        self._ensure_gemini_local_key()
        command = self.cli_config.get("command", "/opt/homebrew/bin/node")
        script_path = self.cli_config.get("script_path", "/Users/lmsx/gemini-cli.js")

        prompt = (
            "请严格遵守下面的 system 指令，再处理 user 请求。\n\n"
            f"[system]\n{system_prompt}\n\n"
            f"[user]\n{user_prompt}\n"
        )
        if expect_json:
            prompt += "\n请只输出一个 JSON 对象，不要输出额外说明。"

        completed = subprocess.run(
            [command, script_path, "ask", prompt],
            check=False,
            capture_output=True,
            text=True,
            timeout=self.api_config.get("timeout", 120),
        )
        if completed.returncode != 0:
            error_text = (completed.stderr or completed.stdout).strip()
            raise LLMResponseError(f"Gemini CLI 调用失败: {error_text}")
        return completed.stdout.strip()

    def _gemini_local_config_has_key(self) -> bool:
        config_path = Path.home() / ".config" / "gemini" / "config.json"
        if not config_path.exists():
            return False
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        return config_state(data.get("apiKey")) == "ready"

    def _ensure_gemini_local_key(self) -> None:
        api_key = self.cli_config.get("api_key", "")
        if config_state(api_key) != "ready":
            if self._gemini_local_config_has_key():
                return
            raise LLMConfigError(
                "Gemini CLI backend 需要 llm_cli.api_key 或 ~/.config/gemini/config.json 里的 apiKey。"
            )
        if not self.cli_config.get("sync_key_to_user_config", True):
            return
        config_dir = Path.home() / ".config" / "gemini"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "config.json"
        payload = {"apiKey": api_key}
        config_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


OpenAICompatibleLLM = ProjectLLM
