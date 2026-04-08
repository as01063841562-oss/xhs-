from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import common


class CommonTest(unittest.TestCase):
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
