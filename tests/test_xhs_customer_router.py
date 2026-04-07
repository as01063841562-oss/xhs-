from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from xhs_customer_router import (
    build_state_summary,
    classify_message,
    confirm_copywriting,
    generate_copywriting_draft,
    generate_graphic_draft,
    guard_materials_ready,
    route_message,
)


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

    def test_generate_copywriting_draft_stores_payload_in_state(self) -> None:
        state = {
            "drafts": {"copywriting": None},
        }
        payload = {"cover_title": "标题", "variants": [{"title": "版本1"}]}

        with patch("xhs_customer_router.generate_xhs_payload", return_value=payload) as mock_generate:
            result = generate_copywriting_draft(
                topic="初三数学二次函数",
                audience="武汉家长",
                config={},
                state=state,
                dry_run=True,
            )

        self.assertEqual(result, payload)
        self.assertEqual(state["drafts"]["copywriting"], payload)
        mock_generate.assert_called_once()

    def test_confirm_copywriting_locks_copywriting_and_moves_to_cover(self) -> None:
        state = {
            "current_state": "state_1_copywriting",
            "confirmed": {
                "topic": "初三数学二次函数",
                "title": None,
                "copywriting": None,
                "cover": None,
                "graphics": None,
            },
            "drafts": {
                "copywriting": {"cover_title": "标题", "variants": []},
                "cover_images": ["old-cover.png"],
                "graphic_images": ["old-graphic.png"],
            },
        }

        confirm_copywriting(state)

        self.assertEqual(state["current_state"], "state_2_cover")
        self.assertEqual(state["confirmed"]["copywriting"], {"cover_title": "标题", "variants": []})
        self.assertEqual(state["drafts"]["cover_images"], [])
        self.assertEqual(state["drafts"]["graphic_images"], [])

    def test_generate_graphic_draft_creates_dedicated_graphics_dir(self) -> None:
        state = {"drafts": {"graphic_images": []}}
        payload = {"cover_title": "标题"}

        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            generated = generate_graphic_draft(payload, state, run_dir)

        self.assertEqual(len(generated), 3)
        self.assertTrue(all(path.endswith(".png") for path in generated))
        self.assertEqual(state["drafts"]["graphic_images"], generated)
        self.assertTrue(all("graphics/graphic_" in path for path in generated))

    def test_route_message_returns_summary_without_mutating_state(self) -> None:
        state = {
            "materials_ready": False,
            "current_state": "state_1_copywriting",
            "confirmed": {
                "topic": "初三数学二次函数",
                "title": None,
                "copywriting": None,
                "cover": None,
                "graphics": None,
            },
        }

        with patch("xhs_customer_router.load_state", return_value=state), patch(
            "xhs_customer_router.save_state"
        ) as mock_save:
            result = route_message(
                client_slug="wuhan-tutoring",
                open_id="ou_test",
                message="汇总",
                dry_run=True,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["operation"], "summary")
        self.assertIn("当前会话摘要", result["response"])
        self.assertFalse(result["state_changed"])
        mock_save.assert_not_called()

    def test_route_message_blocks_topic_request_when_materials_not_ready(self) -> None:
        state = {
            "materials_ready": False,
            "current_state": "state_0_topic",
            "confirmed": {
                "topic": None,
                "title": None,
                "copywriting": None,
                "cover": None,
                "graphics": None,
            },
        }

        with patch("xhs_customer_router.load_state", return_value=state), patch(
            "xhs_customer_router.save_state"
        ) as mock_save:
            result = route_message(
                client_slug="wuhan-tutoring",
                open_id="ou_test",
                message="#选题 数学 二次函数",
                dry_run=True,
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "materials_not_ready")
        self.assertFalse(result["state_changed"])
        mock_save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
