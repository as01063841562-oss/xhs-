from __future__ import annotations

import importlib
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
from repository import get_task
from fastapi.testclient import TestClient


class WebAppTest(unittest.TestCase):
    def test_create_task_ignores_spoofed_role_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                app_module = importlib.import_module("web.app")
                importlib.reload(app_module)
                client = TestClient(app_module.app)

                access = app_module.load_access_config(app_module.CLIENT_SLUG)
                client.get(f"/magic-link?token={access['client_token']}")

                response = client.post(
                    "/tasks",
                    data={
                        "title": "武汉中考数学压轴题",
                        "topic": "武汉中考数学压轴题",
                        "audience": "武汉家长",
                        "role": "ops",
                    },
                    follow_redirects=False,
                )

                self.assertEqual(response.status_code, 303)
                task_id = response.headers["location"].rsplit("/", 1)[-1]
                task = get_task("wuhan-tutoring", task_id)
                self.assertEqual(task["created_by_role"], "client")
                self.assertEqual(task["account_key"], "primary")
            finally:
                common.CLIENTS_DIR = original_clients_dir


if __name__ == "__main__":
    unittest.main()
