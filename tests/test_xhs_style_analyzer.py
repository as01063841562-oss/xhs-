from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import common
from xhs_customer_state import load_state
from xhs_style_analyzer import (
    analyze_articles,
    analyze_images,
    compute_materials_ready,
    generate_style_guides,
    render_image_guide,
    render_writing_guide,
)


class XhsStyleAnalyzerTest(unittest.TestCase):
    def test_analyze_articles_counts_samples_and_access_levels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.md").write_text(
                "# 置顶\n\n- access_level: full_note\n",
                encoding="utf-8",
            )
            (root / "b.md").write_text(
                "# 想找武汉靠谱的陪伴式规划服务？\n\n- access_level: profile_card\n",
                encoding="utf-8",
            )

            report = analyze_articles(root)

            self.assertEqual(report["sample_count"], 2)
            self.assertEqual(report["full_note_count"], 1)
            self.assertEqual(report["profile_card_count"], 1)
            self.assertNotIn("置顶", report["title_examples"])
            self.assertIn("想找武汉靠谱的陪伴式规划服务？", report["title_examples"])

    def test_analyze_images_reads_sizes_and_palette(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Image.new("RGB", (1080, 1440), (255, 255, 255)).save(root / "a.png")
            Image.new("RGB", (1242, 1660), (10, 20, 30)).save(root / "b.jpg")

            report = analyze_images(root)

            self.assertEqual(report["sample_count"], 2)
            self.assertIn([1080, 1440], report["common_sizes"])
            self.assertTrue(report["top_colors"])

    def test_compute_materials_ready_requires_three_full_note_articles_and_three_images(self) -> None:
        self.assertTrue(
            compute_materials_ready(
                {"sample_count": 3, "full_note_count": 3},
                {"sample_count": 3},
            )
        )
        self.assertFalse(
            compute_materials_ready(
                {"sample_count": 3, "full_note_count": 0},
                {"sample_count": 3},
            )
        )
        self.assertFalse(
            compute_materials_ready(
                {"sample_count": 2, "full_note_count": 2},
                {"sample_count": 3},
            )
        )

    def test_render_writing_guide_warns_when_only_profile_card_samples_exist(self) -> None:
        report = {
            "sample_count": 3,
            "full_note_count": 0,
            "profile_card_count": 3,
            "avg_length": 120,
            "title_examples": [
                "总是理不顺？武汉龙门这家值得先了解🔥",
                "想找武汉靠谱的陪伴式规划服务？",
            ],
        }

        guide = render_writing_guide(report)

        self.assertIn("profile-card 快照", guide)
        self.assertIn("不要把下面约束当成完整正文模板", guide)
        self.assertIn("总是理不顺？武汉龙门这家值得先了解🔥", guide)

    def test_generate_style_guides_writes_guides_and_reports_materials_not_ready_for_partial_articles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_root_dir = common.ROOT_DIR
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.ROOT_DIR = Path(temp_dir)
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                refs = common.get_client_root("wuhan-tutoring") / "references"
                article_dir = refs / "article"
                image_dir = refs / "images"
                article_dir.mkdir(parents=True, exist_ok=True)
                image_dir.mkdir(parents=True, exist_ok=True)

                for index, title in enumerate(
                    [
                        "总是理不顺？武汉龙门这家值得先了解🔥",
                        "想找武汉靠谱的陪伴式规划服务？",
                        "武汉中考提分怎么少走弯路",
                    ],
                    start=1,
                ):
                    (article_dir / f"{index}.md").write_text(
                        f"# {title}\n\n- access_level: profile_card\n",
                        encoding="utf-8",
                    )
                for index, color in enumerate([(255, 255, 255), (10, 20, 30), (200, 40, 60)], start=1):
                    Image.new("RGB", (1080, 1440), color).save(image_dir / f"{index}.png")

                result = generate_style_guides("wuhan-tutoring")

                writing_guide = (refs / "文案风格指南.md").read_text(encoding="utf-8")
                image_guide = (refs / "图片风格模板.md").read_text(encoding="utf-8")

                self.assertFalse(result["materials_ready"])
                self.assertIn("profile-card 快照", writing_guide)
                self.assertIn("主色参考", image_guide)
            finally:
                common.ROOT_DIR = original_root_dir
                common.CLIENTS_DIR = original_clients_dir

    def test_generate_style_guides_persists_materials_gate_for_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_root_dir = common.ROOT_DIR
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.ROOT_DIR = Path(temp_dir)
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                refs = common.get_client_root("wuhan-tutoring") / "references"
                article_dir = refs / "article"
                image_dir = refs / "images"
                article_dir.mkdir(parents=True, exist_ok=True)
                image_dir.mkdir(parents=True, exist_ok=True)

                for index, title in enumerate(
                    [
                        "武汉中考数学提分怎么少走弯路",
                        "武汉中考英语作文万能模板",
                        "武汉中考全年备考时间线",
                    ],
                    start=1,
                ):
                    (article_dir / f"{index}.md").write_text(
                        f"# {title}\n\n- access_level: full_note\n",
                        encoding="utf-8",
                    )
                for index, color in enumerate([(255, 255, 255), (10, 20, 30), (200, 40, 60)], start=1):
                    Image.new("RGB", (1080, 1440), color).save(image_dir / f"{index}.png")

                result = generate_style_guides("wuhan-tutoring")
                state = load_state("wuhan-tutoring", "ou_test_runtime")

                self.assertTrue(result["materials_ready"])
                self.assertTrue(state["materials_ready"])
            finally:
                common.ROOT_DIR = original_root_dir
                common.CLIENTS_DIR = original_clients_dir


if __name__ == "__main__":
    unittest.main()
