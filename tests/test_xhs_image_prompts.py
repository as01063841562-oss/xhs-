from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import xhs_image_prompts


def sample_payload() -> dict[str, object]:
    return {
        "title": "武汉初三提分",
        "cover_title": "武汉初三提分",
        "variants": [
            {
                "title": "家长最怕提分没方向",
                "angle": "本地校区 + 提分规划",
                "body": "先定位薄弱点。再安排分层练习。最后盯住提分节奏。",
            },
            {
                "title": "到校先看这三件事",
                "angle": "真实到校体验",
                "body": "先看课堂状态。再看老师节奏。最后看校区动线。",
            },
        ],
    }


class XhsImagePromptsTest(unittest.TestCase):
    maxDiff = None

    def test_load_image_prompt_templates_uses_new_machine_readable_families(self) -> None:
        templates = xhs_image_prompts.load_image_prompt_templates("wuhan-tutoring")

        self.assertEqual(
            set((templates.get("cover_templates") or {}).keys()),
            {"promo_blast", "promo_collage", "promo_map"},
        )
        self.assertEqual(
            set((templates.get("graphics_templates") or {}).keys()),
            {"info_card_blue", "pain_solution", "onsite_overlay"},
        )

        required_fields = {"label", "layout_mode", "headline_style", "accent_palette", "cta_text", "prompt"}
        for family in (templates.get("cover_templates") or {}).values():
            self.assertTrue(required_fields.issubset(family.keys()))
        for family in (templates.get("graphics_templates") or {}).values():
            self.assertTrue(required_fields.issubset(family.keys()))

    def test_ensure_template_state_defaults_and_normalizes_legacy_keys(self) -> None:
        templates = xhs_image_prompts.load_image_prompt_templates("wuhan-tutoring")

        fresh_state: dict[str, object] = {}
        fresh_templates = xhs_image_prompts.ensure_template_state(fresh_state, templates)
        self.assertEqual(fresh_templates["cover_template_key"], "promo_blast")
        self.assertEqual(fresh_templates["graphics_template_key"], "info_card_blue")

        legacy_expectations = [
            ("map_coverage", "promo_map"),
            ("campus_access", "promo_collage"),
            ("parent_consult", "promo_blast"),
        ]
        for old_key, new_key in legacy_expectations:
            with self.subTest(old_key=old_key):
                state = {
                    "image_templates": {
                        "cover_template_key": old_key,
                        "graphics_template_key": "study_plan",
                    }
                }
                template_state = xhs_image_prompts.ensure_template_state(state, templates)
                self.assertEqual(template_state["cover_template_key"], new_key)
                self.assertEqual(state["image_templates"]["cover_template_key"], new_key)

        legacy_graphic_expectations = [
            ("classroom_focus", "onsite_overlay"),
            ("study_plan", "pain_solution"),
            ("brand_trust", "info_card_blue"),
        ]
        for old_key, new_key in legacy_graphic_expectations:
            with self.subTest(old_key=old_key):
                state = {
                    "image_templates": {
                        "cover_template_key": "parent_consult",
                        "graphics_template_key": old_key,
                    }
                }
                template_state = xhs_image_prompts.ensure_template_state(state, templates)
                self.assertEqual(template_state["graphics_template_key"], new_key)
                self.assertEqual(state["image_templates"]["graphics_template_key"], new_key)

    def test_build_cover_prompt_supports_new_promo_cover_families(self) -> None:
        family_expectations = {
            "promo_blast": ["高密度教培投放图", "大字", "强 CTA", "红橙黄"],
            "promo_collage": ["拼贴", "真实校园", "强 CTA"],
            "promo_map": ["地图", "本地校区", "强 CTA"],
        }

        for family_name, markers in family_expectations.items():
            with self.subTest(family_name=family_name):
                state = {
                    "image_templates": {
                        "cover_template_key": family_name,
                        "graphics_template_key": "info_card_blue",
                    }
                }
                prompt = xhs_image_prompts.build_cover_prompt(sample_payload(), state, "wuhan-tutoring")
                for marker in markers:
                    self.assertIn(marker, prompt)

    def test_build_graphic_prompts_supports_new_graphic_families(self) -> None:
        family_expectations = {
            "info_card_blue": ["蓝白信息卡", "3到5块", "家长一眼扫懂"],
            "pain_solution": ["痛点", "解决动作", "3到5块"],
            "onsite_overlay": ["实拍底图", "叠字信息块", "3到5块"],
        }

        for family_name, markers in family_expectations.items():
            with self.subTest(family_name=family_name):
                state = {
                    "image_templates": {
                        "cover_template_key": "promo_blast",
                        "graphics_template_key": family_name,
                    }
                }
                prompts = xhs_image_prompts.build_graphic_prompts(sample_payload(), state, "wuhan-tutoring")
                self.assertEqual(
                    [name for name, _ in prompts],
                    ["graphic_1.png", "graphic_2.png"],
                )
                self.assertEqual(len(prompts), 2)
                joined = "\n".join(prompt for _, prompt in prompts)
                for marker in markers:
                    self.assertIn(marker, joined)


if __name__ == "__main__":
    unittest.main()
