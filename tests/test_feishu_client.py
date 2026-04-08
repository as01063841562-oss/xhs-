from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

if "requests" not in sys.modules:
    sys.modules["requests"] = types.SimpleNamespace(post=None)
if "yaml" not in sys.modules:
    sys.modules["yaml"] = types.SimpleNamespace(safe_load=lambda *_args, **_kwargs: {})

from feishu_client import FeishuClient


class FeishuClientTest(unittest.TestCase):
    def test_send_review_card_uses_refresh_button_contract(self) -> None:
        client = FeishuClient.__new__(FeishuClient)
        captured: dict[str, object] = {}

        def fake_send_message(msg_type: str, content: dict[str, object]) -> str:
            captured["msg_type"] = msg_type
            captured["content"] = content
            return "msg_123"

        client._send_message = fake_send_message  # type: ignore[method-assign]

        message_id = client.send_review_card(
            image_key=["img_cover", "img_graphic"],
            title="待审核",
            content="请确认图文内容",
            tags="#教培",
            note_id="note-123",
        )

        self.assertEqual(message_id, "msg_123")
        self.assertEqual(captured["msg_type"], "interactive")

        card = captured["content"]
        assert isinstance(card, dict)
        action_block = next(element for element in card["elements"] if element["tag"] == "action")
        actions = action_block["actions"]

        self.assertEqual(
            [action["value"]["decision"] for action in actions],
            ["approve", "refresh_cover", "refresh_graphics"],
        )
        self.assertEqual(
            [action["text"]["content"] for action in actions],
            ["✅ 通过", "刷新封面图", "刷新内容配图"],
        )
        self.assertTrue(all(action["value"]["action"] == "xhs_review" for action in actions))
        self.assertTrue(all(action["value"]["note_id"] == "note-123" for action in actions))


if __name__ == "__main__":
    unittest.main()
