from __future__ import annotations

import unittest
from pathlib import Path

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from xhs_customer_router import build_state_summary, classify_message, guard_materials_ready


class XhsCustomerRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {
            "materials_ready": False,
            "current_state": "state_1_copywriting",
            "confirmed": {
                "topic": "初三数学必考-二次函数题型全梳理",
                "title": "二次函数这几个题型一定会考",
                "copywriting": None,
                "cover": None,
                "graphics": None,
            },
        }

    def test_build_state_summary_includes_key_fields(self) -> None:
        summary = build_state_summary(self.state)

        self.assertIn("materials_ready: false", summary)
        self.assertIn("current_state: state_1_copywriting", summary)
        self.assertIn("confirmed.topic: 初三数学必考-二次函数题型全梳理", summary)

    def test_classify_message_detects_topic_requests(self) -> None:
        self.assertEqual(
            classify_message("#选题 初三数学", self.state)["intent"],
            "topic_request",
        )
        self.assertEqual(
            classify_message("有没有中考英语知识点总结", self.state)["intent"],
            "topic_request",
        )

    def test_classify_message_detects_cover_and_graphic_requests(self) -> None:
        self.assertEqual(
            classify_message("帮我生成封面图", self.state)["intent"],
            "cover_request",
        )
        self.assertEqual(
            classify_message("生成配图", self.state)["intent"],
            "graphic_request",
        )
        self.assertEqual(
            classify_message("封面图换成中考冲刺风", self.state)["intent"],
            "cover_request",
        )
        self.assertEqual(
            classify_message("配图换成中考数学题讲解风格", self.state)["intent"],
            "graphic_request",
        )

    def test_classify_message_detects_feedback_and_fallback(self) -> None:
        self.assertEqual(
            classify_message("标题换一个", self.state)["intent"],
            "feedback_request",
        )
        self.assertEqual(
            classify_message("封面图换个背景色", self.state)["intent"],
            "feedback_request",
        )
        self.assertEqual(
            classify_message("给我确认一下", self.state)["intent"],
            "selection_or_confirmation",
        )

    def test_guard_materials_ready_blocks_material_requests(self) -> None:
        for intent in ("topic_request", "selection_or_confirmation", "cover_request", "graphic_request"):
            result = guard_materials_ready(self.state, intent)
            self.assertFalse(result["allowed"])
            self.assertEqual(result["reason"], "materials_not_ready")

    def test_guard_materials_ready_allows_when_ready(self) -> None:
        ready_state = dict(self.state)
        ready_state["materials_ready"] = True

        result = guard_materials_ready(ready_state, "cover_request")

        self.assertTrue(result["allowed"])
        self.assertEqual(result["intent"], "cover_request")


if __name__ == "__main__":
    unittest.main()
