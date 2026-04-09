from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
WEB_DIR = Path(__file__).resolve().parents[1] / "web"
for path in (SCRIPT_DIR, WEB_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import common
from repository import create_task
from repository import update_task
from services import build_action_message, set_materials_gate, sync_task_from_runtime


class WebServicesTest(unittest.TestCase):
    def test_build_action_message_maps_stage_actions(self) -> None:
        task = {
            "topic": "武汉中考数学压轴题",
            "current_state": "state_2_cover",
        }

        self.assertEqual(build_action_message(task, "generate-topic", {}), "#选题 武汉中考数学压轴题")
        self.assertEqual(build_action_message(task, "generate-cover", {}), "生成封面图")
        self.assertEqual(build_action_message(task, "confirm-current", {}), "这张封面图可以，继续")

    def test_sync_task_from_runtime_pulls_state_and_review_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                task = create_task(
                    client_slug="wuhan-tutoring",
                    title="武汉中考数学压轴题",
                    topic="武汉中考数学压轴题",
                    audience="武汉家长",
                    created_by_role="client",
                    account_key="account-a",
                )
                update_task(
                    "wuhan-tutoring",
                    task["task_id"],
                    {
                        "current_state": "state_4_done",
                        "status": "stale",
                    },
                )
                state_path = (
                    common.get_client_root("wuhan-tutoring")
                    / "state"
                    / "feishu_dm"
                    / f"{task['open_id']}.json"
                )
                state_path.write_text(
                    json.dumps(
                        {
                            "materials_ready": True,
                            "current_state": "state_1_copywriting",
                            "session_output_dir": str(Path(temp_dir) / "session-a"),
                            "confirmed": {"topic": "武汉中考数学压轴题"},
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                session_dir = Path(temp_dir) / "session-a"
                session_dir.mkdir(parents=True, exist_ok=True)
                (session_dir / "review_state.json").write_text(
                    json.dumps({"current_review_message_id": "om_test", "status": "waiting_review"}, ensure_ascii=False),
                    encoding="utf-8",
                )
                (session_dir / "result.json").write_text(
                    json.dumps({"status": "waiting_review"}, ensure_ascii=False),
                    encoding="utf-8",
                )

                synced = sync_task_from_runtime("wuhan-tutoring", task)

                self.assertEqual(synced["current_state"], "state_1_copywriting")
                self.assertEqual(synced["status"], "waiting_review")
                self.assertTrue(synced["materials_ready"])
                self.assertEqual(synced["review_message_id"], "om_test")
                self.assertEqual(synced["runtime_status"], "waiting_review")
                self.assertEqual(synced["account_key"], "account-a")
            finally:
                common.CLIENTS_DIR = original_clients_dir

    def test_set_materials_gate_writes_explicit_override_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                result = set_materials_gate("wuhan-tutoring", True)
                gate_path = common.get_client_root("wuhan-tutoring") / "state" / "materials_gate.json"

                self.assertTrue(result["materials_ready"])
                self.assertTrue(gate_path.exists())
                self.assertIn('"materials_ready": true', gate_path.read_text(encoding="utf-8"))
            finally:
                common.CLIENTS_DIR = original_clients_dir


if __name__ == "__main__":
    unittest.main()
