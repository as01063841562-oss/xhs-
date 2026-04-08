from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import xhs_feishu_flow


def sample_payload() -> dict[str, object]:
    return {
        "positioning": "面向武汉家长的教培内容",
        "cover_title": "二次函数提分攻略",
        "cover_prompt": "武汉教培招生图，突出二次函数提分路径。",
        "hashtags": ["武汉中考", "数学提分", "教培运营"],
        "publish_checklist": ["人工复核文案", "人工确认图片内容"],
        "variants": [
            {
                "title": "二次函数想提分，先抓这三步",
                "angle": "提分路径",
                "body": "先看题型，再看易错点，最后做分层训练。",
            },
            {
                "title": "家长最该盯住的不是刷题量",
                "angle": "家长视角",
                "body": "先把薄弱点拆出来，再安排针对性训练。",
            },
            {
                "title": "中考前两个月，数学复习这样排",
                "angle": "冲刺节奏",
                "body": "题型梳理、错题回放、限时模拟要同步推进。",
            },
        ],
    }


def review_state(
    run_dir: Path,
    payload: dict[str, object],
    *,
    message_id: str = "msg_current",
    slide_paths: list[str] | None = None,
    image_keys: list[str] | None = None,
    topic: str = "二次函数提分攻略",
    topic_data_style: str | None = None,
) -> dict[str, object]:
    slide_paths = slide_paths or [str(run_dir / "cover.png")]
    image_keys = image_keys or ["img_cover_old"]
    return {
        "status": "waiting_review",
        "topic": topic,
        "audience": "武汉家长",
        "dry_run": False,
        "skip_image": False,
        "payload": payload,
        "slide_paths": list(slide_paths),
        "image_keys": list(image_keys),
        "cover_path": slide_paths[0],
        "image_key": image_keys[0],
        "current_review_message_id": message_id,
        "note_id": "note-001",
        "revision_count": 0,
        "topic_data_style": topic_data_style,
    }


class XhsFeishuFlowTest(unittest.TestCase):
    maxDiff = None

    def test_main_accepts_refresh_actions_in_resume_mode(self) -> None:
        for action in ("refresh_cover", "refresh_graphics"):
            with self.subTest(action=action):
                with patch.object(
                    xhs_feishu_flow,
                    "resume_review_action",
                    return_value={"status": "waiting_review", "steps": {"action": action}},
                ) as mock_resume, patch.object(
                    sys,
                    "argv",
                    [
                        "xhs_feishu_flow.py",
                        "--mode",
                        "resume",
                        "--action",
                        action,
                        "--message-id",
                        "msg-123",
                        "--json",
                    ],
                ), patch("sys.stdout", new_callable=io.StringIO) as stdout:
                    xhs_feishu_flow.main()

                mock_resume.assert_called_once()
                self.assertEqual(mock_resume.call_args.kwargs["action"], action)
                self.assertIn("__JSON_RESULT__", stdout.getvalue())

    def test_resume_review_action_refresh_cover_keeps_payload_and_reissues_review_card(self) -> None:
        payload = sample_payload()
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            state = review_state(run_dir, payload)
            refreshed_cover = run_dir / "cover_refresh_1.png"
            feishu = MagicMock()
            feishu.send_review_card.return_value = "msg_cover_refresh_1"

            def fake_generate_image(
                prompt: str,
                output_path: str | Path | None = None,
                config: dict[str, object] | None = None,
                allow_placeholder: bool = True,
            ) -> Path:
                del prompt, config, allow_placeholder
                target = Path(output_path or refreshed_cover)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"png")
                return target

            with patch.object(xhs_feishu_flow, "load_review_state", return_value=(run_dir, state)), patch.object(
                xhs_feishu_flow, "load_config", return_value={}
            ), patch.object(
                xhs_feishu_flow, "_match_topic_data", return_value=None
            ), patch.object(
                xhs_feishu_flow, "generate_image", side_effect=fake_generate_image
            ) as mock_generate_image, patch.object(
                xhs_feishu_flow, "render_image"
            ) as mock_render_image, patch.object(
                xhs_feishu_flow, "upload_slide_images", return_value=["img_cover_new"]
            ) as mock_upload, patch.object(
                xhs_feishu_flow, "FeishuClient", return_value=feishu
            ), patch.object(
                xhs_feishu_flow, "generate_xhs_payload"
            ) as mock_generate_payload, patch.object(
                xhs_feishu_flow, "send_revision_request"
            ) as mock_send_revision, patch.object(
                xhs_feishu_flow, "save_review_state"
            ), patch.object(
                xhs_feishu_flow, "_save_result"
            ), patch.object(
                xhs_feishu_flow, "timestamp", return_value="2026-04-08T10:00:00"
            ):
                result = xhs_feishu_flow.resume_review_action("refresh_cover", "msg_current")

        self.assertEqual(result["status"], "waiting_review")
        self.assertEqual(result["steps"]["action"], "refresh_cover")
        self.assertEqual(state["payload"], payload)
        self.assertEqual(state["image_keys"], ["img_cover_new"])
        self.assertEqual(state["image_key"], "img_cover_new")
        self.assertEqual(state["current_review_message_id"], "msg_cover_refresh_1")
        self.assertEqual(state["review_action_mode"], "image_refresh")
        self.assertEqual(state["cover_refresh_count"], 1)
        self.assertIsNone(state.get("pending_revision_mode"))
        mock_generate_payload.assert_not_called()
        mock_send_revision.assert_not_called()
        mock_generate_image.assert_called_once()
        mock_render_image.assert_not_called()
        mock_upload.assert_called_once()
        feishu.send_review_card.assert_called_once()

    def test_resume_review_action_refresh_graphics_only_updates_graphics_lane(self) -> None:
        payload = sample_payload()
        topic_data = {
            "title": "二次函数提分攻略",
            "subtitle": "武汉家长高频关注点",
            "style": "info_card",
            "tags": ["武汉中考", "二次函数"],
            "key_points": ["先抓基础题", "再看函数图像", "最后做压轴题拆解"],
        }
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            cover_path = run_dir / "slides" / "slide_1.png"
            graphic_one = run_dir / "slides" / "slide_2.png"
            graphic_two = run_dir / "slides" / "slide_3.png"
            state = review_state(
                run_dir,
                payload,
                slide_paths=[str(cover_path), str(graphic_one), str(graphic_two)],
                image_keys=["img_cover_old", "img_graphic_old_1", "img_graphic_old_2"],
                topic_data_style="info_card",
            )
            feishu = MagicMock()
            feishu.send_review_card.return_value = "msg_graphics_refresh_1"

            def fake_render_image(topic: dict[str, object], output_path: Path | str, width: int = 1080, height: int = 1440) -> Path:
                del topic, width, height
                target = Path(output_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"png")
                return target

            with patch.object(xhs_feishu_flow, "load_review_state", return_value=(run_dir, state)), patch.object(
                xhs_feishu_flow, "load_config", return_value={}
            ), patch.object(
                xhs_feishu_flow, "_match_topic_data", return_value=topic_data
            ), patch.object(
                xhs_feishu_flow, "render_image", side_effect=fake_render_image
            ) as mock_render_image, patch.object(
                xhs_feishu_flow, "generate_image"
            ) as mock_generate_image, patch.object(
                xhs_feishu_flow, "upload_slide_images", return_value=["img_graphic_new_1", "img_graphic_new_2"]
            ) as mock_upload, patch.object(
                xhs_feishu_flow, "FeishuClient", return_value=feishu
            ), patch.object(
                xhs_feishu_flow, "generate_xhs_payload"
            ) as mock_generate_payload, patch.object(
                xhs_feishu_flow, "send_revision_request"
            ) as mock_send_revision, patch.object(
                xhs_feishu_flow, "save_review_state"
            ), patch.object(
                xhs_feishu_flow, "_save_result"
            ), patch.object(
                xhs_feishu_flow, "timestamp", return_value="2026-04-08T10:05:00"
            ):
                result = xhs_feishu_flow.resume_review_action("refresh_graphics", "msg_current")

        self.assertEqual(result["status"], "waiting_review")
        self.assertEqual(result["steps"]["action"], "refresh_graphics")
        self.assertEqual(state["payload"], payload)
        self.assertEqual(state["slide_paths"][0], str(cover_path))
        self.assertEqual(state["cover_path"], str(cover_path))
        self.assertEqual(state["image_key"], "img_cover_old")
        self.assertEqual(
            state["image_keys"],
            ["img_cover_old", "img_graphic_new_1", "img_graphic_new_2"],
        )
        self.assertEqual(state["current_review_message_id"], "msg_graphics_refresh_1")
        self.assertEqual(state["review_action_mode"], "image_refresh")
        self.assertEqual(state["graphics_refresh_count"], 1)
        self.assertIsNone(state.get("pending_revision_mode"))
        mock_generate_payload.assert_not_called()
        mock_send_revision.assert_not_called()
        self.assertEqual(mock_render_image.call_count, 2)
        mock_generate_image.assert_not_called()
        mock_upload.assert_called_once()
        feishu.send_review_card.assert_called_once()

    def test_resume_review_action_refresh_graphics_reports_when_no_graphics_lane_exists(self) -> None:
        payload = sample_payload()
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            state = review_state(run_dir, payload, topic_data_style=None)

            with patch.object(xhs_feishu_flow, "load_review_state", return_value=(run_dir, state)), patch.object(
                xhs_feishu_flow, "load_config", return_value={}
            ), patch.object(
                xhs_feishu_flow, "_match_topic_data", return_value=None
            ), patch.object(
                xhs_feishu_flow, "render_image"
            ) as mock_render_image, patch.object(
                xhs_feishu_flow, "generate_image"
            ) as mock_generate_image, patch.object(
                xhs_feishu_flow, "upload_slide_images"
            ) as mock_upload, patch.object(
                xhs_feishu_flow, "FeishuClient"
            ) as mock_feishu, patch.object(
                xhs_feishu_flow, "save_review_state"
            ), patch.object(
                xhs_feishu_flow, "_save_result"
            ):
                result = xhs_feishu_flow.resume_review_action("refresh_graphics", "msg_current")

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "no_distinct_graphics_lane")
        self.assertEqual(state["current_review_message_id"], "msg_current")
        mock_render_image.assert_not_called()
        mock_generate_image.assert_not_called()
        mock_upload.assert_not_called()
        mock_feishu.assert_not_called()

    def test_resume_review_action_modify_remains_compatible_for_legacy_cards(self) -> None:
        payload = sample_payload()
        revised_payload = sample_payload()
        revised_payload["cover_title"] = "修改版｜二次函数提分攻略"
        revised_payload["cover_prompt"] = "修改版封面提示词"
        revised_payload["variants"] = [
            {
                "title": "修改版标题",
                "angle": "修改版角度",
                "body": "修改后的正文。",
            }
        ]
        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            state = {
                "status": "waiting_review",
                "topic": "二次函数提分攻略",
                "audience": "武汉家长",
                "dry_run": False,
                "skip_image": False,
                "payload": payload,
                "cover_path": str(run_dir / "cover_old.png"),
                "image_key": "img_cover_old",
                "current_review_message_id": "msg_current",
                "note_id": "note-001",
                "revision_count": 0,
            }
            feishu = MagicMock()
            feishu.send_review_card.return_value = "msg_modify_1"

            with patch.object(xhs_feishu_flow, "load_review_state", return_value=(run_dir, state)), patch.object(
                xhs_feishu_flow, "load_config", return_value={}
            ), patch.object(
                xhs_feishu_flow, "generate_xhs_payload", return_value=revised_payload
            ) as mock_generate_payload, patch.object(
                xhs_feishu_flow, "generate_cover_art", return_value=run_dir / "cover_new.png"
            ) as mock_generate_cover, patch.object(
                xhs_feishu_flow, "upload_cover_image", return_value="img_cover_new"
            ) as mock_upload_cover, patch.object(
                xhs_feishu_flow, "FeishuClient", return_value=feishu
            ), patch.object(
                xhs_feishu_flow, "save_review_state"
            ), patch.object(
                xhs_feishu_flow, "_save_result"
            ), patch.object(
                xhs_feishu_flow, "timestamp", return_value="2026-04-08T10:10:00"
            ):
                result = xhs_feishu_flow.resume_review_action(
                    "modify",
                    "msg_current",
                    revision_notes="标题再直接一点",
                    revision_scope="copywriting",
                )

        self.assertEqual(result["status"], "waiting_review")
        self.assertEqual(result["steps"]["action"], "modify")
        self.assertEqual(state["payload"], revised_payload)
        self.assertEqual(state["cover_path"], str(run_dir / "cover_new.png"))
        self.assertEqual(state["image_key"], "img_cover_new")
        self.assertEqual(state["current_review_message_id"], "msg_modify_1")
        self.assertEqual(state["revision_count"], 1)
        self.assertEqual(state["review_action_mode"], "revision")
        self.assertEqual(state["last_revision_notes"], "标题再直接一点")
        self.assertEqual(state["last_revision_scope"], "copywriting")
        mock_generate_payload.assert_called_once()
        mock_generate_cover.assert_called_once()
        mock_upload_cover.assert_called_once()
        feishu.send_review_card.assert_called_once()

    def test_main_rejects_refresh_actions_in_request_edit_mode(self) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "xhs_feishu_flow.py",
                "--mode",
                "request-edit",
                "--action",
                "refresh_cover",
                "--message-id",
                "msg-123",
            ],
        ):
            with self.assertRaisesRegex(SystemExit, "modify/rewrite"):
                xhs_feishu_flow.main()


if __name__ == "__main__":
    unittest.main()
