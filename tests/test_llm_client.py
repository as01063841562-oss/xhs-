from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from requests import Response

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from llm_client import ProjectLLM


class LLMClientTest(unittest.TestCase):
    def test_openai_compatible_decodes_utf8_json_when_response_encoding_is_latin1(self) -> None:
        client = ProjectLLM(
            {
                "llm_api": {
                    "backend": "openai_compatible",
                    "base_url": "https://xuedingtoken.com/v1",
                    "api_key": "sk-test",
                    "model": "claude-sonnet-4-6",
                }
            }
        )

        response = Response()
        response.status_code = 200
        response.encoding = "ISO-8859-1"
        response.headers["content-type"] = "text/event-stream"
        response._content = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": "武汉娃必看！这份升学攻略让孩子少走三年弯路",
                        }
                    }
                ]
            },
            ensure_ascii=False,
        ).encode("utf-8")

        with patch("llm_client.requests.post", return_value=response):
            content = client.chat("system", "user")

        self.assertEqual(content, "武汉娃必看！这份升学攻略让孩子少走三年弯路")


if __name__ == "__main__":
    unittest.main()
