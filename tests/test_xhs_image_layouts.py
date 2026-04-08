from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageChops, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import xhs_image_layouts


def create_base_image(path: Path) -> None:
    image = Image.new("RGB", (1080, 1440), color=(238, 230, 216))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 960, 1080, 1440), fill=(222, 214, 196))
    draw.rounded_rectangle((250, 250, 830, 1230), radius=80, fill=(79, 133, 196))
    draw.ellipse((350, 360, 730, 740), fill=(255, 228, 196))
    draw.rectangle((430, 730, 650, 1140), fill=(240, 150, 94))
    image.save(path, "PNG")


def region_changed(before: Image.Image, after: Image.Image, box: tuple[int, int, int, int]) -> bool:
    diff = ImageChops.difference(before.crop(box), after.crop(box)).convert("RGB")
    return diff.getbbox() is not None


class XhsImageLayoutsTest(unittest.TestCase):
    def test_render_base_image_overlay_creates_1080x1440_promo_output(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            base_path = tmp_path / "base.png"
            output_path = tmp_path / "promo.png"
            create_base_image(base_path)

            rendered = xhs_image_layouts.render_base_image_overlay(
                base_image_path=base_path,
                output_path=output_path,
                template_family="promo_blast",
                main_title="初升高冲刺提分",
                sub_title="到店测评后直接给方案",
                selling_points=["武汉本地校区", "老师现场答疑", "试听路线清楚"],
                cta_text="点击咨询领取方案",
            )

            self.assertEqual(rendered, output_path)
            self.assertTrue(output_path.exists())

            before = Image.open(base_path).convert("RGBA")
            after = Image.open(output_path).convert("RGBA")
            self.assertEqual(after.size, (1080, 1440))
            self.assertTrue(region_changed(before, after, (40, 40, 1040, 420)))
            self.assertTrue(region_changed(before, after, (80, 1180, 1000, 1400)))
            self.assertFalse(region_changed(before, after, (420, 520, 660, 900)))

    def test_render_base_image_overlay_supports_blue_info_card_graphic(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            base_path = tmp_path / "base.png"
            output_path = tmp_path / "info_card.png"
            create_base_image(base_path)

            xhs_image_layouts.render_base_image_overlay(
                base_image_path=base_path,
                output_path=output_path,
                template_family="info_card_blue",
                main_title="家长最想先看什么",
                sub_title="先给动作，不要长段落",
                selling_points=["先做学情定位", "再排提分节奏", "最后约试听沟通"],
                cta_text="私信领取试听安排",
            )

            before = Image.open(base_path).convert("RGBA")
            after = Image.open(output_path).convert("RGBA")

            self.assertEqual(after.size, (1080, 1440))
            self.assertTrue(region_changed(before, after, (70, 860, 1010, 1340)))

    def test_render_base_image_overlay_supports_onsite_overlay_with_trust_points(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            base_path = tmp_path / "base.png"
            output_path = tmp_path / "onsite.png"
            create_base_image(base_path)

            xhs_image_layouts.render_base_image_overlay(
                base_image_path=base_path,
                output_path=output_path,
                template_family="onsite_overlay",
                main_title="真实校区沟通现场",
                sub_title="咨询动作和信任背书一起讲",
                trust_points=["老师当面讲方案", "校区路线明确", "试听与测评可落地"],
                cta_text="预约到店沟通",
            )

            before = Image.open(base_path).convert("RGBA")
            after = Image.open(output_path).convert("RGBA")

            self.assertEqual(after.size, (1080, 1440))
            self.assertTrue(region_changed(before, after, (70, 760, 1010, 1360)))
            self.assertFalse(region_changed(before, after, (440, 520, 640, 860)))


if __name__ == "__main__":
    unittest.main()
