from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def load_feishu_client_class():
    fake_requests = types.ModuleType("requests")
    fake_requests.post = None
    fake_yaml = types.ModuleType("yaml")
    fake_yaml.safe_load = lambda *_args, **_kwargs: {}

    original_common = sys.modules.pop("common", None)
    original_feishu_client = sys.modules.pop("feishu_client", None)
    try:
        with patch.dict(
            sys.modules,
            {"requests": fake_requests, "yaml": fake_yaml},
            clear=False,
        ):
            module = importlib.import_module("feishu_client")
            return module.FeishuClient
    finally:
        sys.modules.pop("common", None)
        sys.modules.pop("feishu_client", None)
        if original_common is not None:
            sys.modules["common"] = original_common
        if original_feishu_client is not None:
            sys.modules["feishu_client"] = original_feishu_client


class FeishuClientTest(unittest.TestCase):
    def test_send_review_card_uses_refresh_button_contract(self) -> None:
        original_requests = sys.modules.get("requests")
        original_yaml = sys.modules.get("yaml")
        FeishuClient = load_feishu_client_class()

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
        self.assertIs(sys.modules.get("requests"), original_requests)
        self.assertIs(sys.modules.get("yaml"), original_yaml)


if __name__ == "__main__":
    unittest.main()
