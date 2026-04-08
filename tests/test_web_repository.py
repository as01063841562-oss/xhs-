from __future__ import annotations

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
from xhs_customer_state import load_state
from repository import (
    create_task,
    ensure_access_config,
    get_task,
    list_tasks,
    update_task,
)


class WebRepositoryTest(unittest.TestCase):
    def test_create_task_persists_registry_and_bootstraps_state_file(self) -> None:
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
                )

                loaded = get_task("wuhan-tutoring", task["task_id"])
                state = load_state("wuhan-tutoring", task["open_id"])

                self.assertEqual(loaded["title"], "武汉中考数学压轴题")
                self.assertEqual(loaded["current_state"], "state_0_topic")
                self.assertEqual(loaded["created_by_role"], "client")
                self.assertEqual(loaded["account_key"], "primary")
                self.assertTrue(task["open_id"].startswith("web_task_"))
                self.assertEqual(state["current_state"], "state_0_topic")
            finally:
                common.CLIENTS_DIR = original_clients_dir

    def test_create_task_preserves_custom_account_key(self) -> None:
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

                self.assertEqual(task["account_key"], "account-a")
                self.assertEqual(get_task("wuhan-tutoring", task["task_id"])["account_key"], "account-a")
            finally:
                common.CLIENTS_DIR = original_clients_dir

    def test_update_task_merges_new_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                task = create_task(
                    client_slug="wuhan-tutoring",
                    title="武汉中考数学压轴题",
                    topic="武汉中考数学压轴题",
                    audience="武汉家长",
                    created_by_role="ops",
                )

                updated = update_task(
                    "wuhan-tutoring",
                    task["task_id"],
                    {
                        "current_state": "state_1_copywriting",
                        "review_message_id": "om_test",
                    },
                )

                self.assertEqual(updated["current_state"], "state_1_copywriting")
                self.assertEqual(updated["review_message_id"], "om_test")
            finally:
                common.CLIENTS_DIR = original_clients_dir

    def test_ensure_access_config_creates_stable_ops_and_client_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"

                first = ensure_access_config("wuhan-tutoring")
                second = ensure_access_config("wuhan-tutoring")

                self.assertEqual(first["ops_token"], second["ops_token"])
                self.assertEqual(first["client_token"], second["client_token"])
                self.assertIn("secret_key", first)
            finally:
                common.CLIENTS_DIR = original_clients_dir

    def test_list_tasks_returns_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                first = create_task(
                    client_slug="wuhan-tutoring",
                    title="任务 A",
                    topic="任务 A",
                    audience="武汉家长",
                    created_by_role="client",
                )
                second = create_task(
                    client_slug="wuhan-tutoring",
                    title="任务 B",
                    topic="任务 B",
                    audience="武汉家长",
                    created_by_role="ops",
                )

                tasks = list_tasks("wuhan-tutoring")

                self.assertEqual(tasks[0]["task_id"], second["task_id"])
                self.assertEqual(tasks[1]["task_id"], first["task_id"])
            finally:
                common.CLIENTS_DIR = original_clients_dir


if __name__ == "__main__":
    unittest.main()
