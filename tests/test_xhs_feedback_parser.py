from __future__ import annotations

import unittest
from pathlib import Path

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from xhs_feedback_parser import parse_feedback


class XhsFeedbackParserTest(unittest.TestCase):
    def test_parse_feedback_summary(self) -> None:
        result = parse_feedback("帮我汇总一下当前内容", "state_2_cover")

        self.assertEqual(result["operation"], "summary")
        self.assertIsNone(result.get("target_state"))

    def test_parse_feedback_explicit_edit_beats_summary(self) -> None:
        result = parse_feedback("标题换一个，顺便汇总", "state_1_copywriting")

        self.assertEqual(result["operation"], "partial_update")
        self.assertEqual(result["scope"], {"type": "title"})
        self.assertEqual(result["instruction"], "顺便汇总")

    def test_parse_feedback_rollback_to_copywriting(self) -> None:
        result = parse_feedback("回到文案", "state_3_graphics")

        self.assertEqual(result["operation"], "rollback")
        self.assertEqual(result["target_state"], "state_1_copywriting")

    def test_parse_feedback_regenerate_current_stage(self) -> None:
        result = parse_feedback("重新来当前阶段", "state_2_cover")

        self.assertEqual(result["operation"], "regenerate_current")
        self.assertEqual(result["target_state"], "state_2_cover")

    def test_parse_feedback_regenerate_cover_from_stage(self) -> None:
        result = parse_feedback("重新来封面图", "state_2_cover")

        self.assertEqual(result["operation"], "regenerate_current")
        self.assertEqual(result["target_state"], "state_2_cover")

    def test_parse_feedback_title_update(self) -> None:
        result = parse_feedback("标题换一个，更简洁一点", "state_1_copywriting")

        self.assertEqual(result["operation"], "partial_update")
        self.assertEqual(result["scope"], {"type": "title"})
        self.assertEqual(result["instruction"], "更简洁一点")

    def test_parse_feedback_paragraph_update(self) -> None:
        result = parse_feedback("文案第2段再压缩一下，减少术语", "state_1_copywriting")

        self.assertEqual(result["operation"], "partial_update")
        self.assertEqual(result["scope"], {"type": "paragraph", "index": 2})
        self.assertEqual(result["instruction"], "再压缩一下，减少术语")

    def test_parse_feedback_cover_background_update(self) -> None:
        result = parse_feedback("封面图背景换成浅蓝色，更干净", "state_2_cover")

        self.assertEqual(result["operation"], "partial_update")
        self.assertEqual(result["target_state"], "state_2_cover")
        self.assertEqual(result["scope"], {"type": "cover_background"})
        self.assertEqual(result["instruction"], "换成浅蓝色，更干净")

    def test_parse_feedback_graphic_style_update(self) -> None:
        result = parse_feedback("配图整体更简洁一点，少一点花哨", "state_3_graphics")

        self.assertEqual(result["operation"], "partial_update")
        self.assertEqual(result["target_state"], "state_3_graphics")
        self.assertEqual(result["scope"], {"type": "graphic_style"})
        self.assertEqual(result["instruction"], "整体更简洁一点，少一点花哨")

    def test_parse_feedback_cover_change_with_background_variant(self) -> None:
        result = parse_feedback("封面图换成中考冲刺风", "state_2_cover")

        self.assertEqual(result["operation"], "partial_update")
        self.assertEqual(result["target_state"], "state_2_cover")
        self.assertEqual(result["scope"], {"type": "cover_background"})
        self.assertEqual(result["instruction"], "中考冲刺风")

    def test_parse_feedback_unknown_fallback(self) -> None:
        result = parse_feedback("顺便看一下这个", "state_1_copywriting")

        self.assertEqual(result["operation"], "unknown")


if __name__ == "__main__":
    unittest.main()
