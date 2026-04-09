from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import common


class CommonTest(unittest.TestCase):
    def test_load_openclaw_config_supports_json5_include_and_env_secret_ref(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "OPENCLAW_SECRET_FEISHU_APP_SECRET=feishu-secret\n"
                "OPENCLAW_SECRET_ANTHROPIC_API_KEY=anthropic-secret\n",
                encoding="utf-8",
            )
            (root / "openclaw.json").write_text(
                "{\n"
                "  // aggregator\n"
                "  $include: [\n"
                "    \"./10-models.json5\",\n"
                "    \"./30-channels.json5\",\n"
                "  ],\n"
                "}\n",
                encoding="utf-8",
            )
            (root / "10-models.json5").write_text(
                "{\n"
                "  models: {\n"
                "    providers: {\n"
                "      openai: { baseUrl: \"https://x.example/v1\", models: [] },\n"
                "      anthropic: {\n"
                "        apiKey: { source: \"env\", id: \"OPENCLAW_SECRET_ANTHROPIC_API_KEY\" },\n"
                "        models: [],\n"
                "      },\n"
                "    },\n"
                "  },\n"
                "  agents: { defaults: { model: { primary: \"anthropic/claude-sonnet-4-6\" } } },\n"
                "}\n",
                encoding="utf-8",
            )
            (root / "30-channels.json5").write_text(
                "{\n"
                "  channels: {\n"
                "    feishu: {\n"
                "      appId: \"cli_demo\",\n"
                "      appSecret: { source: \"env\", id: \"OPENCLAW_SECRET_FEISHU_APP_SECRET\" },\n"
                "    },\n"
                "  },\n"
                "}\n",
                encoding="utf-8",
            )

            loaded = common.load_openclaw_config(str(root / "openclaw.json"))

        self.assertEqual(loaded["channels"]["feishu"]["appSecret"], "feishu-secret")
        self.assertEqual(loaded["models"]["providers"]["anthropic"]["apiKey"], "anthropic-secret")
        self.assertEqual(loaded["models"]["providers"]["openai"]["baseUrl"], "https://x.example/v1")

    def test_resolve_llm_api_config_uses_openclaw_defaults(self) -> None:
        llm_api = {
            "backend": "openai_compatible",
            "timeout": 120,
        }
        openclaw_config = {
            "models": {
                "providers": {
                    "openai": {"baseUrl": "https://xuedingtoken.com/v1"},
                    "anthropic": {"apiKey": "sk-test-anthropic"},
                },
            },
            "agents": {
                "defaults": {
                    "model": {
                        "primary": "anthropic/claude-sonnet-4-6",
                    },
                },
            },
        }

        resolved = common.resolve_llm_api_config(llm_api, openclaw_config)

        self.assertEqual(resolved["backend"], "openai_compatible")
        self.assertEqual(resolved["base_url"], "https://xuedingtoken.com/v1")
        self.assertEqual(resolved["api_key"], "sk-test-anthropic")
        self.assertEqual(resolved["model"], "claude-sonnet-4-6")


if __name__ == "__main__":
    unittest.main()
