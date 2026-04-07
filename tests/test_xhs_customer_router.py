from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import common
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

    def test_classify_message_treats_stage_approval_as_confirmation(self) -> None:
        cover_state = {
            "current_state": "state_2_cover",
        }
        graphic_state = {
            "current_state": "state_3_graphics",
        }

        self.assertEqual(
            classify_message("这张封面图可以，继续", cover_state)["intent"],
            "selection_or_confirmation",
        )
        self.assertEqual(
            classify_message("这组配图可以，继续", graphic_state)["intent"],
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

    def test_generate_copywriting_draft_passes_customer_prompt_and_style_guide(self) -> None:
        with TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                client_root = common.get_client_root("wuhan-tutoring")
                (client_root / "prompts").mkdir(parents=True, exist_ok=True)
                (client_root / "references").mkdir(parents=True, exist_ok=True)
                (client_root / "prompts" / "system-prompt.md").write_text(
                    "# 武汉教培系统提示词\n禁止未确认自动推进。",
                    encoding="utf-8",
                )
                (client_root / "references" / "文案风格指南.md").write_text(
                    "# 文案风格指南\n标题优先家长决策场景。",
                    encoding="utf-8",
                )
                state = {"drafts": {"copywriting": None}}

                with patch("xhs_customer_router.generate_xhs_payload", return_value={"cover_title": "标题"}) as mock_generate:
                    generate_copywriting_draft(
                        topic="初三数学二次函数",
                        audience="武汉家长",
                        config={},
                        state=state,
                        dry_run=False,
                        client_slug="wuhan-tutoring",
                    )

                self.assertEqual(mock_generate.call_args.kwargs["system_prompt_text"], "# 武汉教培系统提示词\n禁止未确认自动推进。")
                self.assertEqual(mock_generate.call_args.kwargs["style_guide_text"], "# 文案风格指南\n标题优先家长决策场景。")
            finally:
                common.CLIENTS_DIR = original_clients_dir

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
            generated = generate_graphic_draft(payload, state, run_dir, dry_run=True)

        self.assertEqual(len(generated), 3)
        self.assertTrue(all(path.endswith(".png") for path in generated))
        self.assertEqual(state["drafts"]["graphic_images"], generated)
        self.assertTrue(all("graphics/graphic_" in path for path in generated))

    def test_generate_graphic_draft_uses_renderer_outside_dry_run(self) -> None:
        state = {"drafts": {"graphic_images": []}}
        payload = {
            "cover_title": "标题",
            "hashtags": ["武汉中考", "数学"],
            "variants": [
                {"title": "图1", "angle": "角度1", "body": "第一点。第二点。第三点。"},
                {"title": "图2", "angle": "角度2", "body": "A。B。C。"},
                {"title": "图3", "angle": "角度3", "body": "甲。乙。丙。"},
            ],
        }

        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)

            def fake_render(topic, output_path):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"png")
                return output_path

            with patch("xhs_customer_router.render_image", side_effect=fake_render) as mock_render:
                generated = generate_graphic_draft(payload, state, run_dir, dry_run=False)

        self.assertEqual(len(generated), 3)
        self.assertEqual(mock_render.call_count, 3)
        self.assertEqual(state["drafts"]["graphic_images"], generated)

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

    def test_route_message_generates_topic_drafts_when_materials_are_ready(self) -> None:
        state = {
            "materials_ready": True,
            "current_state": "state_0_topic",
            "confirmed": {
                "topic": None,
                "title": None,
                "copywriting": None,
                "cover": None,
                "graphics": None,
            },
            "drafts": {
                "topics": [],
                "copywriting": None,
                "cover_images": [],
                "graphic_images": [],
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

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action"], "generate_topic_drafts")
        self.assertTrue(result["state_changed"])
        self.assertGreaterEqual(len(result["topic_options"]), 1)
        self.assertGreaterEqual(len(state["drafts"]["topics"]), 1)
        self.assertTrue(any("二次函数" in item["title"] or "数学" in item["title"] for item in result["topic_options"]))
        mock_save.assert_not_called()

    def test_route_message_selects_topic_and_generates_copywriting_draft(self) -> None:
        state = {
            "materials_ready": True,
            "current_state": "state_0_topic",
            "confirmed": {
                "topic": None,
                "title": None,
                "copywriting": None,
                "cover": None,
                "graphics": None,
            },
            "drafts": {
                "topics": [
                    {
                        "title": "初三数学必考：二次函数题型全梳理",
                        "angle": "掌握这些题型轻松拿高分",
                        "tags": ["二次函数", "中考数学"],
                        "reference_style": "info_card",
                        "audience": "初三学生家长",
                    }
                ],
                "copywriting": None,
                "cover_images": [],
                "graphic_images": [],
            },
        }
        payload = {"cover_title": "标题", "variants": [{"title": "版本1"}]}

        with patch("xhs_customer_router.load_state", return_value=state), patch(
            "xhs_customer_router.save_state"
        ) as mock_save, patch("xhs_customer_router.generate_xhs_payload", return_value=payload):
            result = route_message(
                client_slug="wuhan-tutoring",
                open_id="ou_test",
                message="我选第一个",
                dry_run=True,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action"], "confirm_topic_and_generate_copywriting_draft")
        self.assertEqual(state["confirmed"]["topic"], "初三数学必考：二次函数题型全梳理")
        self.assertEqual(state["current_state"], "state_1_copywriting")
        self.assertEqual(state["drafts"]["copywriting"], payload)
        self.assertTrue(result["state_changed"])
        mock_save.assert_not_called()

    def test_route_message_confirms_copywriting_and_moves_to_cover(self) -> None:
        state = {
            "materials_ready": True,
            "current_state": "state_1_copywriting",
            "confirmed": {
                "topic": "初三数学必考：二次函数题型全梳理",
                "title": None,
                "copywriting": None,
                "cover": None,
                "graphics": None,
            },
            "drafts": {
                "topics": [],
                "copywriting": {"cover_title": "标题", "variants": [{"title": "版本1"}]},
                "cover_images": [],
                "graphic_images": [],
            },
        }

        with patch("xhs_customer_router.load_state", return_value=state), patch(
            "xhs_customer_router.save_state"
        ) as mock_save:
            result = route_message(
                client_slug="wuhan-tutoring",
                open_id="ou_test",
                message="这个文案可以，继续",
                dry_run=True,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action"], "confirm_copywriting")
        self.assertEqual(state["current_state"], "state_2_cover")
        self.assertEqual(state["confirmed"]["copywriting"], {"cover_title": "标题", "variants": [{"title": "版本1"}]})
        self.assertTrue(result["state_changed"])
        mock_save.assert_not_called()

    def test_route_message_confirms_cover_and_moves_to_graphics(self) -> None:
        state = {
            "materials_ready": True,
            "current_state": "state_2_cover",
            "confirmed": {
                "topic": "初三数学必考：二次函数题型全梳理",
                "title": None,
                "copywriting": {"cover_title": "标题", "variants": [{"title": "版本1"}]},
                "cover": None,
                "graphics": None,
            },
            "drafts": {
                "topics": [],
                "copywriting": {"cover_title": "标题", "variants": [{"title": "版本1"}]},
                "cover_images": ["cover1.png", "cover2.png"],
                "graphic_images": [],
            },
        }

        with patch("xhs_customer_router.load_state", return_value=state), patch(
            "xhs_customer_router.save_state"
        ) as mock_save:
            result = route_message(
                client_slug="wuhan-tutoring",
                open_id="ou_test",
                message="这张封面图可以，继续",
                dry_run=True,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action"], "confirm_cover")
        self.assertEqual(state["current_state"], "state_3_graphics")
        self.assertEqual(state["confirmed"]["cover"], ["cover1.png", "cover2.png"])
        self.assertTrue(result["state_changed"])
        mock_save.assert_not_called()

    def test_route_message_confirms_graphics_and_moves_to_done(self) -> None:
        state = {
            "materials_ready": True,
            "current_state": "state_3_graphics",
            "confirmed": {
                "topic": "初三数学必考：二次函数题型全梳理",
                "title": None,
                "copywriting": {"cover_title": "标题", "variants": [{"title": "版本1"}]},
                "cover": ["cover1.png"],
                "graphics": None,
            },
            "drafts": {
                "topics": [],
                "copywriting": {"cover_title": "标题", "variants": [{"title": "版本1"}]},
                "cover_images": ["cover1.png"],
                "graphic_images": ["g1.png", "g2.png"],
            },
        }

        with patch("xhs_customer_router.load_state", return_value=state), patch(
            "xhs_customer_router.save_state"
        ) as mock_save:
            result = route_message(
                client_slug="wuhan-tutoring",
                open_id="ou_test",
                message="这组配图可以，继续",
                dry_run=True,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action"], "confirm_graphics")
        self.assertEqual(state["current_state"], "state_4_done")
        self.assertEqual(state["confirmed"]["graphics"], ["g1.png", "g2.png"])
        self.assertTrue(result["state_changed"])
        mock_save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
