from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import common
from xhs_customer_state import (
    default_state,
    ensure_session_dir,
    load_state,
    reset_after_copywriting,
    save_state,
    state_path,
)


class XhsCustomerStateTest(unittest.TestCase):
    def test_default_state_starts_in_state_0_topic(self) -> None:
        state = default_state()

        self.assertEqual(state["current_state"], "state_0_topic")
        self.assertIsNone(state["confirmed"]["topic"])
        self.assertEqual(state["drafts"]["topics"], [])

    def test_save_and_load_round_trip_uses_feishu_dm_state_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                expected_path = state_path("wuhan-tutoring", "open-123")
                state = default_state()
                state["confirmed"]["topic"] = "初三数学必考-二次函数题型全梳理"
                state["drafts"]["topics"] = [{"title": "A"}]

                saved_path = save_state("wuhan-tutoring", "open-123", state)
                loaded = load_state("wuhan-tutoring", "open-123")

                self.assertEqual(
                    expected_path,
                    Path(temp_dir) / "clients" / "wuhan-tutoring" / "state" / "feishu_dm" / "open-123.json",
                )
                self.assertEqual(saved_path, expected_path)
                self.assertTrue(saved_path.exists())
                self.assertEqual(loaded, state)
            finally:
                common.CLIENTS_DIR = original_clients_dir

    def test_load_state_normalizes_partial_persisted_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                path = state_path("wuhan-tutoring", "open-123")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "current_state": "state_2_cover",
                            "confirmed": {"topic": "已确认主题"},
                            "drafts": {"topics": [{"title": "备选"}]},
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

                loaded = load_state("wuhan-tutoring", "open-123")

                self.assertEqual(loaded["current_state"], "state_2_cover")
                self.assertEqual(loaded["confirmed"]["topic"], "已确认主题")
                self.assertIsNone(loaded["confirmed"]["title"])
                self.assertEqual(loaded["drafts"]["topics"], [{"title": "备选"}])
                self.assertIsNone(loaded["drafts"]["copywriting"])
                self.assertEqual(loaded["materials_ready"], False)
                self.assertEqual(loaded["updated_at"], "")
            finally:
                common.CLIENTS_DIR = original_clients_dir

    def test_state_path_and_load_state_do_not_create_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                path = state_path("wuhan-tutoring", "open-123")

                self.assertFalse(path.parent.exists())
                self.assertEqual(
                    load_state("wuhan-tutoring", "open-123"),
                    default_state(),
                )
                self.assertFalse(path.parent.exists())
            finally:
                common.CLIENTS_DIR = original_clients_dir

    def test_save_state_updates_updated_at_before_persisting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                state = default_state()

                with patch("common.timestamp", return_value="20260407-123456"):
                    save_state("wuhan-tutoring", "open-123", state)

                loaded = load_state("wuhan-tutoring", "open-123")

                self.assertEqual(loaded["updated_at"], "20260407-123456")
            finally:
                common.CLIENTS_DIR = original_clients_dir

    def test_ensure_session_dir_uses_timestamped_directory_and_reuses_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                state = default_state()

                with patch("common.timestamp", return_value="20260407-123456"):
                    session_dir = ensure_session_dir("wuhan-tutoring", "open-123", state)

                self.assertEqual(
                    session_dir,
                    Path(temp_dir)
                    / "clients"
                    / "wuhan-tutoring"
                    / "output"
                    / "sessions"
                    / "open-123-20260407-123456",
                )
                self.assertEqual(state["session_output_dir"], str(session_dir))
                self.assertTrue(session_dir.exists())

                state["session_output_dir"] = str(session_dir)
                with patch("common.timestamp", return_value="20260407-999999"):
                    reused = ensure_session_dir("wuhan-tutoring", "open-123", state)

                self.assertEqual(reused, session_dir)
            finally:
                common.CLIENTS_DIR = original_clients_dir

    def test_reset_after_copywriting_keeps_confirmed_topic_and_clears_downstream(self) -> None:
        state = default_state()
        state["current_state"] = "state_2_cover"
        state["current_topic_id"] = "topic-1"
        state["confirmed"]["topic"] = "初三数学必考-二次函数题型全梳理"
        state["confirmed"]["title"] = "标题"
        state["confirmed"]["copywriting"] = "正文"
        state["confirmed"]["cover"] = {"file": "cover.png"}
        state["confirmed"]["graphics"] = [{"file": "g1.png"}]
        state["drafts"]["topics"] = [{"title": "备选"}]
        state["drafts"]["copywriting"] = "草稿"
        state["drafts"]["cover_images"] = ["cover-draft.png"]
        state["drafts"]["graphic_images"] = ["graphic-draft.png"]

        reset_after_copywriting(state)

        self.assertEqual(state["current_state"], "state_1_copywriting")
        self.assertEqual(state["confirmed"]["topic"], "初三数学必考-二次函数题型全梳理")
        self.assertIsNone(state["confirmed"]["title"])
        self.assertIsNone(state["confirmed"]["copywriting"])
        self.assertIsNone(state["confirmed"]["cover"])
        self.assertIsNone(state["confirmed"]["graphics"])
        self.assertEqual(state["drafts"]["topics"], [])
        self.assertIsNone(state["drafts"]["copywriting"])
        self.assertEqual(state["drafts"]["cover_images"], [])
        self.assertEqual(state["drafts"]["graphic_images"], [])


if __name__ == "__main__":
    unittest.main()
