from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import gemini_web_image


class FakeLocator:
    def __init__(
        self,
        *,
        count: int = 1,
        visible: bool = True,
        attrs: dict[str, str] | None = None,
        text: str = "",
        on_click=None,
    ) -> None:
        self._count = count
        self._visible = visible
        self._attrs = dict(attrs or {})
        self._text = text
        self.click_count = 0
        self._on_click = on_click
        self.first = self

    def count(self) -> int:
        return self._count

    def is_visible(self) -> bool:
        return self._visible

    def click(self, *args, **kwargs) -> None:
        del args, kwargs
        self.click_count += 1
        if self._on_click:
            self._on_click()

    def get_attribute(self, name: str) -> str | None:
        return self._attrs.get(name)

    def inner_text(self) -> str:
        return self._text

    def set_attribute(self, name: str, value: str) -> None:
        self._attrs[name] = value


class FakePage:
    def __init__(
        self,
        *,
        image_mode_active: bool = False,
        prompt_placeholder: str = "이미지를 설명하세요",
        style_picker_active: bool = False,
    ) -> None:
        self.drawer_button = FakeLocator(attrs={"aria-expanded": "false"})
        self.image_mode_chip = FakeLocator(count=1 if image_mode_active else 0)
        self.image_mode_menu_item = FakeLocator(
            on_click=lambda: self.image_mode_chip.__dict__.update({"_count": 1, "_visible": True})
        )
        self.prompt_box = FakeLocator(attrs={"placeholder": prompt_placeholder})
        self.rich_prompt_box = FakeLocator(attrs={"contenteditable": "true"})
        self.style_button = FakeLocator()
        self.stop_button = FakeLocator(count=0, visible=False)
        self.image_copy_button = FakeLocator(count=0, visible=False, attrs={"aria-label": "이미지 복사"})
        self.body = FakeLocator(
            text="이미지에 어울리는 스타일을 고르세요" if style_picker_active else ""
        )
        self.wait_calls: list[int] = []
        self.locator_calls: list[str] = []
        self.role_calls: list[tuple[str, str | None]] = []

    def locator(self, selector: str) -> FakeLocator:
        self.locator_calls.append(selector)
        if selector == "button.toolbox-drawer-button-with-label":
            return self.drawer_button
        if selector == "textarea:visible":
            return self.prompt_box
        if selector == '[role="textbox"]:visible':
            return FakeLocator(count=0, visible=False)
        if selector == '[contenteditable="true"]:visible':
            return self.rich_prompt_box
        if selector == "body":
            return self.body
        raise AssertionError(f"unexpected selector: {selector}")

    def get_by_role(self, role: str, name=None) -> FakeLocator:
        self.role_calls.append((role, name.pattern if hasattr(name, "pattern") else str(name) if name is not None else None))
        if role == "button" and isinstance(name, re.Pattern) and "이미지 만들기 선택 해제" in name.pattern:
            return self.image_mode_chip
        if role == "button" and isinstance(name, re.Pattern) and "대답 생성 중지" in name.pattern:
            return self.stop_button
        if role == "button" and name == "이미지 복사":
            return self.image_copy_button
        if role == "button" and isinstance(name, re.Pattern) and "이미지 복사" in name.pattern:
            return self.image_copy_button
        if role == "button" and isinstance(name, re.Pattern) and "천연색" in name.pattern:
            return self.style_button
        if role == "menuitemcheckbox" and isinstance(name, re.Pattern) and "이미지 만들기" in name.pattern:
            return self.image_mode_menu_item
        if role == "button" and isinstance(name, re.Pattern) and "이미지 만들기" in name.pattern:
            return self.image_mode_menu_item
        if role == "button" and isinstance(name, re.Pattern) and "Create image" in name.pattern:
            return self.image_mode_menu_item
        raise AssertionError(f"unexpected role request: role={role!r}, name={name!r}")

    def get_by_text(self, text):
        pattern = text.pattern if hasattr(text, "pattern") else str(text)
        if "이미지 만들기" in pattern or "Create image" in pattern:
            return self.image_mode_menu_item
        if "천연색" in pattern:
            return self.style_button
        raise AssertionError(f"unexpected text request: {text!r}")

    def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)


class GeminiWebImageTest(unittest.TestCase):
    def test_first_clickable_skips_hidden_candidate_and_uses_visible_one(self) -> None:
        hidden = FakeLocator(visible=False)
        visible = FakeLocator()

        target = gemini_web_image._first_clickable(None, [hidden, visible], 2_000)

        self.assertIs(target, visible)
        self.assertEqual(hidden.click_count, 0)
        self.assertEqual(visible.click_count, 1)

    def test_ensure_image_mode_opens_drawer_and_clicks_image_tile(self) -> None:
        page = FakePage(image_mode_active=False)

        gemini_web_image._ensure_image_mode(page, 2_000)

        self.assertEqual(page.drawer_button.click_count, 1)
        self.assertEqual(page.image_mode_menu_item.click_count, 1)
        self.assertGreaterEqual(len(page.wait_calls), 1)

    def test_ensure_image_mode_is_noop_when_already_active(self) -> None:
        page = FakePage(image_mode_active=True)

        gemini_web_image._ensure_image_mode(page, 2_000)

        self.assertEqual(page.drawer_button.click_count, 0)
        self.assertEqual(page.image_mode_menu_item.click_count, 0)

    def test_wait_for_image_prompt_box_returns_prompt_textarea(self) -> None:
        page = FakePage(prompt_placeholder="이미지를 설명하세요")

        prompt_box = gemini_web_image._wait_for_image_prompt_box(page, 1_000)

        self.assertIs(prompt_box, page.prompt_box)

    def test_wait_for_image_prompt_box_falls_back_to_contenteditable_box(self) -> None:
        page = FakePage(prompt_placeholder="")
        page.prompt_box = FakeLocator(count=0, visible=False)

        prompt_box = gemini_web_image._wait_for_image_prompt_box(page, 1_000)

        self.assertIs(prompt_box, page.rich_prompt_box)

    def test_ensure_image_style_keeps_style_picker_unselected(self) -> None:
        page = FakePage(style_picker_active=True)

        gemini_web_image._ensure_image_style(page, 2_000)

        self.assertEqual(page.style_button.click_count, 0)

    def test_wait_for_image_result_ready_waits_for_stop_to_clear_then_copy_button(self) -> None:
        page = FakePage()
        page.stop_button = FakeLocator(count=1, visible=True)
        page.body = FakeLocator(text="Creating your image...")
        page.image_copy_button = FakeLocator(count=0, visible=False, attrs={"aria-label": "이미지 복사"})
        ready = {"value": False}

        def advance_state(_ms: int) -> None:
            page.stop_button = FakeLocator(count=0, visible=False)
            page.body = FakeLocator(text="")
            page.image_copy_button = FakeLocator(count=1, visible=True, attrs={"aria-label": "이미지 복사"})
            ready["value"] = True
            page.wait_calls.append(_ms)

        page.wait_for_timeout = advance_state  # type: ignore[method-assign]

        def fake_wait_for_visible_button(_page, _names, _timeout_ms):
            if ready["value"]:
                return page.image_copy_button
            raise gemini_web_image.GeminiWebImageError("not ready")

        original = gemini_web_image._wait_for_visible_button
        gemini_web_image._wait_for_visible_button = fake_wait_for_visible_button
        try:
            gemini_web_image._wait_for_image_result_ready(page, 2_000)
        finally:
            gemini_web_image._wait_for_visible_button = original

        self.assertGreaterEqual(len(page.wait_calls), 1)


if __name__ == "__main__":
    unittest.main()
