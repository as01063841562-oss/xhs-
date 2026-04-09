#!/usr/bin/env python3
"""Local Pillow overlay renderer for customer-provided Wuhan tutoring images."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

OUTPUT_SIZE = (1080, 1440)

PROMO_FAMILIES = {"promo_blast", "promo_collage", "promo_map"}
CONTENT_FAMILIES = {"info_card_blue", "pain_solution", "onsite_overlay"}
LEGACY_TEMPLATE_ALIASES = {
    "parent_consult": "promo_blast",
    "campus_access": "promo_collage",
    "map_coverage": "promo_map",
    "classroom_focus": "info_card_blue",
    "study_plan": "pain_solution",
    "brand_trust": "onsite_overlay",
}
FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
)

_FONT_CACHE: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


@dataclass(frozen=True, slots=True)
class OverlayRenderRequest:
    base_image_path: Path
    template_family: str
    main_title: str
    sub_title: str = ""
    selling_points: tuple[str, ...] = field(default_factory=tuple)
    trust_points: tuple[str, ...] = field(default_factory=tuple)
    cta_text: str = ""

    @classmethod
    def create(
        cls,
        *,
        base_image_path: Path | str,
        template_family: str,
        main_title: str,
        sub_title: str = "",
        selling_points: Sequence[str] | None = None,
        trust_points: Sequence[str] | None = None,
        cta_text: str = "",
    ) -> "OverlayRenderRequest":
        return cls(
            base_image_path=Path(base_image_path),
            template_family=_normalize_template_family(template_family),
            main_title=str(main_title or "").strip(),
            sub_title=str(sub_title or "").strip(),
            selling_points=_normalize_points(selling_points),
            trust_points=_normalize_points(trust_points),
            cta_text=str(cta_text or "").strip(),
        )

    @property
    def points(self) -> tuple[str, ...]:
        if self.selling_points:
            return self.selling_points
        if self.trust_points:
            return self.trust_points
        if self.sub_title:
            return (self.sub_title,)
        return ()


def render_base_image_overlay(
    *,
    base_image_path: Path | str,
    output_path: Path | str,
    template_family: str,
    main_title: str,
    sub_title: str = "",
    selling_points: Sequence[str] | None = None,
    trust_points: Sequence[str] | None = None,
    cta_text: str = "",
) -> Path:
    request = OverlayRenderRequest.create(
        base_image_path=base_image_path,
        template_family=template_family,
        main_title=main_title,
        sub_title=sub_title,
        selling_points=selling_points,
        trust_points=trust_points,
        cta_text=cta_text,
    )

    canvas = _prepare_base_canvas(request.base_image_path)
    overlay = Image.new("RGBA", OUTPUT_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    if request.template_family in PROMO_FAMILIES:
        _render_promo_overlay(draw, request)
    else:
        _render_content_overlay(draw, request)

    rendered = Image.alpha_composite(canvas, overlay).convert("RGB")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered.save(output, "PNG", optimize=True)
    return output


def _normalize_template_family(template_family: str) -> str:
    normalized = LEGACY_TEMPLATE_ALIASES.get(str(template_family or "").strip(), str(template_family or "").strip())
    if normalized in PROMO_FAMILIES or normalized in CONTENT_FAMILIES:
        return normalized
    raise ValueError(f"Unsupported overlay template family: {template_family}")


def _normalize_points(values: Sequence[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    cleaned = tuple(str(value).strip() for value in values if str(value).strip())
    return cleaned[:5]


def _prepare_base_canvas(base_image_path: Path) -> Image.Image:
    base = Image.open(base_image_path).convert("RGB")
    background = ImageOps.fit(base, OUTPUT_SIZE, method=Image.Resampling.LANCZOS)
    background = background.filter(ImageFilter.GaussianBlur(18))
    background = Image.blend(background, Image.new("RGB", OUTPUT_SIZE, (34, 28, 24)), 0.18)

    fitted = ImageOps.contain(base, OUTPUT_SIZE, method=Image.Resampling.LANCZOS)
    canvas = background.convert("RGBA")
    x = (OUTPUT_SIZE[0] - fitted.width) // 2
    y = (OUTPUT_SIZE[1] - fitted.height) // 2
    canvas.alpha_composite(fitted.convert("RGBA"), dest=(x, y))
    return canvas


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    for candidate in FONT_CANDIDATES:
        font_path = Path(candidate)
        if not font_path.exists():
            continue
        try:
            font = ImageFont.truetype(str(font_path), size=size)
            _FONT_CACHE[size] = font
            return font
        except OSError:
            continue
    font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


def _line_height(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, *, stroke_width: int = 0) -> int:
    bbox = draw.textbbox((0, 0), "武汉A", font=font, stroke_width=stroke_width)
    return bbox[3] - bbox[1]


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    *,
    max_lines: int | None = None,
    stroke_width: int = 0,
) -> list[str]:
    content = str(text or "").strip()
    if not content:
        return []

    lines: list[str] = []
    current = ""
    truncated = False

    for char in content:
        if char == "\n":
            if current:
                lines.append(current)
                current = ""
            if max_lines is not None and len(lines) >= max_lines:
                truncated = True
                break
            continue

        candidate = current + char
        bbox = draw.textbbox((0, 0), candidate, font=font, stroke_width=stroke_width)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
            continue

        lines.append(current)
        current = char
        if max_lines is not None and len(lines) >= max_lines:
            truncated = True
            break

    if current and (max_lines is None or len(lines) < max_lines):
        lines.append(current)
    elif current:
        truncated = True

    if truncated and lines:
        last = lines[-1]
        while last:
            candidate = last + "..."
            bbox = draw.textbbox((0, 0), candidate, font=font, stroke_width=stroke_width)
            if bbox[2] - bbox[0] <= max_width:
                lines[-1] = candidate
                break
            last = last[:-1]
        if not last:
            lines[-1] = "..."
    return lines


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    *,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    max_width: int,
    spacing: int = 8,
    max_lines: int | None = None,
    stroke_width: int = 0,
    stroke_fill: tuple[int, int, int, int] | None = None,
) -> int:
    lines = _wrap_text(draw, text, font, max_width, max_lines=max_lines, stroke_width=stroke_width)
    if not lines:
        return xy[1]
    y = xy[1]
    line_height = _line_height(draw, font, stroke_width=stroke_width)
    for line in lines:
        draw.text(
            (xy[0], y),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        y += line_height + spacing
    return y - spacing


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    *,
    box: tuple[int, int, int, int],
    text: str,
    fill: tuple[int, int, int, int],
    text_fill: tuple[int, int, int, int],
    border: tuple[int, int, int, int] | None = None,
    font_size: int = 34,
) -> None:
    draw.rounded_rectangle(box, radius=22, fill=fill, outline=border, width=3 if border else 1)
    font = _load_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = box[0] + ((box[2] - box[0]) - text_width) // 2
    y = box[1] + ((box[3] - box[1]) - text_height) // 2 - 2
    draw.text((x, y), text, font=font, fill=text_fill)


def _draw_points_panel(
    draw: ImageDraw.ImageDraw,
    *,
    start_y: int,
    points: Sequence[str],
    chip_fill: tuple[int, int, int, int],
    chip_border: tuple[int, int, int, int],
) -> int:
    if not points:
        return start_y

    font = _load_font(32)
    y = start_y
    for index, point in enumerate(points[:3], start=1):
        draw.rounded_rectangle((74, y, 820, y + 88), radius=24, fill=chip_fill, outline=chip_border, width=4)
        _draw_pill(
            draw,
            box=(90, y + 14, 164, y + 74),
            text=str(index),
            fill=(215, 41, 41, 255),
            text_fill=(255, 255, 255, 255),
        )
        _draw_wrapped_text(
            draw,
            xy=(188, y + 18),
            text=point,
            font=font,
            fill=(68, 36, 22, 255),
            max_width=610,
            max_lines=1,
        )
        y += 106
    return y


def _render_promo_overlay(draw: ImageDraw.ImageDraw, request: OverlayRenderRequest) -> None:
    title_panel = (48, 42, 1032, 416)
    title_fill = (255, 247, 240, 236)
    border = (226, 47, 26, 255)
    kicker_fill = (255, 205, 72, 255)
    kicker_text = "武汉本地教培"
    cta_text = request.cta_text or "点击咨询领取专属方案"
    chip_fill = (255, 233, 188, 238)
    chip_border = (238, 126, 36, 255)

    if request.template_family == "promo_collage":
        title_panel = (42, 48, 760, 430)
        chip_fill = (255, 243, 214, 240)
        chip_border = (206, 68, 48, 255)
        draw.rounded_rectangle((792, 74, 1014, 286), radius=38, fill=(255, 255, 255, 112), outline=(255, 214, 102, 255), width=6)
        draw.rounded_rectangle((816, 312, 1024, 504), radius=32, fill=(255, 255, 255, 92), outline=(229, 57, 53, 255), width=5)
        kicker_text = "拼图招生图"
    elif request.template_family == "promo_map":
        title_panel = (48, 48, 760, 410)
        chip_fill = (255, 241, 194, 242)
        chip_border = (234, 105, 31, 255)
        draw.rounded_rectangle((782, 86, 1022, 356), radius=34, fill=(255, 248, 236, 228), outline=(242, 85, 27, 255), width=6)
        _draw_pill(
            draw,
            box=(812, 112, 996, 172),
            text="校区覆盖",
            fill=(255, 214, 75, 255),
            text_fill=(110, 38, 8, 255),
            border=(242, 105, 16, 255),
            font_size=28,
        )
        _draw_wrapped_text(
            draw,
            xy=(828, 206),
            text="武汉地图\n就近咨询",
            font=_load_font(48),
            fill=(218, 43, 23, 255),
            max_width=154,
            max_lines=2,
            spacing=14,
        )
        kicker_text = "地图校区图"

    draw.rounded_rectangle(title_panel, radius=40, fill=title_fill, outline=border, width=8)
    _draw_pill(
        draw,
        box=(74, 72, 330, 132),
        text=kicker_text,
        fill=kicker_fill,
        text_fill=(114, 36, 10, 255),
        border=(244, 104, 32, 255),
        font_size=28,
    )

    title_font = _load_font(96)
    subtitle_font = _load_font(34)
    title_end_y = _draw_wrapped_text(
        draw,
        xy=(78, 156),
        text=request.main_title,
        font=title_font,
        fill=(218, 36, 24, 255),
        max_width=title_panel[2] - 110,
        max_lines=3,
        spacing=8,
        stroke_width=3,
        stroke_fill=(255, 252, 246, 255),
    )
    if request.sub_title:
        _draw_pill(
            draw,
            box=(76, min(title_end_y + 24, 318), title_panel[2] - 48, min(title_end_y + 88, 382)),
            text=request.sub_title,
            fill=(66, 23, 14, 214),
            text_fill=(255, 246, 230, 255),
            border=(255, 186, 84, 255),
            font_size=30,
        )

    _draw_points_panel(draw, start_y=934, points=request.points, chip_fill=chip_fill, chip_border=chip_border)

    draw.rounded_rectangle((68, 1198, 1012, 1366), radius=40, fill=(216, 34, 28, 245), outline=(255, 213, 92, 255), width=8)
    draw.rounded_rectangle((92, 1222, 988, 1340), radius=32, fill=(255, 120, 46, 220))
    _draw_wrapped_text(
        draw,
        xy=(140, 1248),
        text=cta_text,
        font=_load_font(50),
        fill=(255, 255, 255, 255),
        max_width=780,
        max_lines=1,
        stroke_width=2,
        stroke_fill=(150, 36, 20, 255),
    )
    _draw_pill(
        draw,
        box=(836, 1238, 974, 1326),
        text="马上约",
        fill=(255, 218, 80, 255),
        text_fill=(125, 40, 12, 255),
        border=(255, 247, 214, 255),
        font_size=28,
    )


def _render_content_overlay(draw: ImageDraw.ImageDraw, request: OverlayRenderRequest) -> None:
    if request.template_family == "info_card_blue":
        _render_info_card_blue(draw, request)
        return
    if request.template_family == "pain_solution":
        _render_pain_solution(draw, request)
        return
    _render_onsite_overlay(draw, request)


def _render_info_card_blue(draw: ImageDraw.ImageDraw, request: OverlayRenderRequest) -> None:
    outer = (58, 836, 1022, 1350)
    header = (58, 836, 1022, 1018)
    draw.rounded_rectangle(outer, radius=42, fill=(248, 251, 255, 238), outline=(34, 96, 189, 255), width=6)
    draw.rounded_rectangle(header, radius=42, fill=(40, 107, 202, 236))
    draw.rounded_rectangle((58, 970, 1022, 1018), radius=0, fill=(40, 107, 202, 236))

    _draw_pill(
        draw,
        box=(88, 868, 290, 924),
        text="蓝白信息卡",
        fill=(232, 241, 255, 255),
        text_fill=(35, 80, 150, 255),
        border=(255, 255, 255, 255),
        font_size=26,
    )
    _draw_wrapped_text(
        draw,
        xy=(90, 948),
        text=request.main_title,
        font=_load_font(60),
        fill=(255, 255, 255, 255),
        max_width=820,
        max_lines=2,
        spacing=6,
    )
    if request.sub_title:
        _draw_wrapped_text(
            draw,
            xy=(90, 1080),
            text=request.sub_title,
            font=_load_font(30),
            fill=(62, 89, 122, 255),
            max_width=840,
            max_lines=2,
        )

    y = 1148
    bullet_font = _load_font(34)
    for index, point in enumerate(request.points[:4], start=1):
        draw.rounded_rectangle((96, y, 984, y + 74), radius=18, fill=(233, 243, 255, 255))
        _draw_pill(
            draw,
            box=(112, y + 9, 178, y + 63),
            text=str(index),
            fill=(44, 104, 198, 255),
            text_fill=(255, 255, 255, 255),
            font_size=26,
        )
        _draw_wrapped_text(
            draw,
            xy=(206, y + 15),
            text=point,
            font=bullet_font,
            fill=(32, 62, 101, 255),
            max_width=740,
            max_lines=1,
        )
        y += 86

    if request.cta_text:
        _draw_pill(
            draw,
            box=(660, 1272, 970, 1334),
            text=request.cta_text,
            fill=(38, 109, 212, 255),
            text_fill=(255, 255, 255, 255),
            border=(219, 234, 255, 255),
            font_size=28,
        )


def _render_pain_solution(draw: ImageDraw.ImageDraw, request: OverlayRenderRequest) -> None:
    draw.rounded_rectangle((70, 840, 1010, 1346), radius=42, fill=(255, 248, 246, 228), outline=(224, 65, 42, 255), width=6)
    _draw_pill(
        draw,
        box=(94, 872, 286, 930),
        text="痛点-方案",
        fill=(228, 54, 47, 255),
        text_fill=(255, 255, 255, 255),
        font_size=26,
    )
    _draw_wrapped_text(
        draw,
        xy=(94, 958),
        text=request.main_title,
        font=_load_font(58),
        fill=(170, 31, 28, 255),
        max_width=840,
        max_lines=2,
        spacing=8,
    )
    if request.sub_title:
        _draw_pill(
            draw,
            box=(94, 1092, 986, 1154),
            text=request.sub_title,
            fill=(255, 232, 187, 255),
            text_fill=(122, 53, 18, 255),
            border=(243, 136, 44, 255),
            font_size=28,
        )

    y = 1186
    colors = (
        ((255, 235, 233, 255), (209, 47, 44, 255)),
        ((232, 243, 255, 255), (32, 92, 176, 255)),
        ((233, 247, 238, 255), (36, 119, 87, 255)),
    )
    for index, point in enumerate(request.points[:3], start=1):
        fill, accent = colors[(index - 1) % len(colors)]
        draw.rounded_rectangle((94, y, 986, y + 86), radius=20, fill=fill, outline=accent, width=3)
        _draw_pill(
            draw,
            box=(110, y + 14, 204, y + 70),
            text=f"{index}",
            fill=accent,
            text_fill=(255, 255, 255, 255),
            font_size=26,
        )
        _draw_wrapped_text(
            draw,
            xy=(228, y + 18),
            text=point,
            font=_load_font(32),
            fill=(64, 44, 38, 255),
            max_width=720,
            max_lines=1,
        )
        y += 96

    if request.cta_text:
        _draw_pill(
            draw,
            box=(658, 1278, 972, 1338),
            text=request.cta_text,
            fill=(38, 104, 198, 255),
            text_fill=(255, 255, 255, 255),
            border=(255, 255, 255, 255),
            font_size=28,
        )


def _render_onsite_overlay(draw: ImageDraw.ImageDraw, request: OverlayRenderRequest) -> None:
    box = (654, 804, 1022, 1348)
    draw.rounded_rectangle(box, radius=40, fill=(23, 34, 54, 196), outline=(255, 181, 70, 255), width=5)
    _draw_pill(
        draw,
        box=(682, 834, 964, 890),
        text="现场讲解叠字",
        fill=(255, 209, 73, 255),
        text_fill=(92, 38, 8, 255),
        border=(255, 247, 226, 255),
        font_size=26,
    )
    title_bottom = _draw_wrapped_text(
        draw,
        xy=(686, 926),
        text=request.main_title,
        font=_load_font(52),
        fill=(255, 255, 255, 255),
        max_width=290,
        max_lines=3,
        spacing=6,
    )
    if request.sub_title:
        _draw_wrapped_text(
            draw,
            xy=(686, min(title_bottom + 18, 1090)),
            text=request.sub_title,
            font=_load_font(28),
            fill=(215, 227, 244, 255),
            max_width=290,
            max_lines=3,
            spacing=6,
        )

    y = 1130
    for point in request.points[:3]:
        draw.rounded_rectangle((684, y, 992, y + 82), radius=18, fill=(245, 247, 251, 228))
        _draw_pill(
            draw,
            box=(698, y + 15, 758, y + 67),
            text="•",
            fill=(233, 89, 38, 255),
            text_fill=(255, 255, 255, 255),
            font_size=28,
        )
        _draw_wrapped_text(
            draw,
            xy=(776, y + 16),
            text=point,
            font=_load_font(28),
            fill=(31, 45, 66, 255),
            max_width=194,
            max_lines=2,
            spacing=4,
        )
        y += 92

    if request.cta_text:
        _draw_pill(
            draw,
            box=(688, 1276, 988, 1338),
            text=request.cta_text,
            fill=(239, 97, 38, 255),
            text_fill=(255, 255, 255, 255),
            border=(255, 223, 180, 255),
            font_size=27,
        )


__all__ = ["OUTPUT_SIZE", "OverlayRenderRequest", "render_base_image_overlay"]
