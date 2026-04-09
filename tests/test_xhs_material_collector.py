from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import ssl

import sys

import yaml

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import common
from xhs_material_collector import (
    build_note_markdown,
    build_note_record,
    build_source_index,
    collect_materials,
    download_binary,
    load_source_profiles,
    parse_args,
    persist_note_record,
)


class XhsMaterialCollectorTest(unittest.TestCase):
    def test_download_binary_retries_with_unverified_ssl_context_for_cert_failure(self) -> None:
        calls: list[dict[str, object]] = []

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

            def read(self) -> bytes:
                return b"image-bytes"

        def fake_urlopen(request, timeout=0, context=None):
            calls.append(
                {
                    "url": request.full_url,
                    "timeout": timeout,
                    "context": context,
                }
            )
            if len(calls) == 1:
                raise URLError(
                    ssl.SSLCertVerificationError(
                        "self-signed certificate in certificate chain"
                    )
                )
            return FakeResponse()

        with patch("xhs_material_collector.urlopen", side_effect=fake_urlopen):
            data = download_binary("https://ci.xiaohongshu.com/cover.jpg")

        self.assertEqual(data, b"image-bytes")
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0]["context"])
        self.assertIsNotNone(calls[1]["context"])

    def test_parse_args_uses_expected_defaults(self) -> None:
        args = parse_args([])

        self.assertEqual(args.client, "wuhan-tutoring")
        self.assertEqual(args.limit_notes, 5)
        self.assertFalse(args.dry_run)
        self.assertEqual(args.cdp_url, "http://127.0.0.1:9227")

    def test_load_source_profiles_reads_client_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                workflow_path = common.get_client_workflow_path("wuhan-tutoring")
                workflow_path.parent.mkdir(parents=True, exist_ok=True)
                workflow_path.write_text(
                    yaml.safe_dump(
                        {
                            "materials": {
                                "source_profiles": [
                                    " https://www.xiaohongshu.com/user/profile/a ",
                                    "https://www.xiaohongshu.com/user/profile/b",
                                ]
                            }
                        },
                        allow_unicode=True,
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )

                self.assertEqual(
                    load_source_profiles("wuhan-tutoring"),
                    [
                        "https://www.xiaohongshu.com/user/profile/a",
                        "https://www.xiaohongshu.com/user/profile/b",
                    ],
                )
            finally:
                common.CLIENTS_DIR = original_clients_dir

    def test_build_note_markdown_records_profile_card_limitations(self) -> None:
        note = {
            "title": "初三数学二次函数避坑点",
            "author": "武汉补习班",
            "source_profile_url": "https://www.xiaohongshu.com/user/profile/abc",
            "collected_via": "chrome_cdp_profile_cards",
            "access_level": "profile_card",
            "note_url": None,
            "image_url": "https://ci.xiaohongshu.com/image.jpg",
        }

        markdown = build_note_markdown(note)

        self.assertIn("# 初三数学二次函数避坑点", markdown)
        self.assertIn("- access_level: profile_card", markdown)
        self.assertIn("- collected_via: chrome_cdp_profile_cards", markdown)
        self.assertIn("full body was not accessible without login", markdown)

    def test_build_note_record_adds_deterministic_output_paths(self) -> None:
        note = build_note_record(
            "wuhan-tutoring",
            {
                "title": "初三数学二次函数避坑点",
                "author": "武汉补习班",
                "source_profile_url": "https://www.xiaohongshu.com/user/profile/6865ebf8000000001e004b42",
                "collected_via": "chrome_cdp_profile_cards",
                "access_level": "profile_card",
                "note_url": None,
                "image_url": "https://ci.xiaohongshu.com/cover.png",
            },
            1,
        )

        self.assertEqual(
            note["article_snapshot_path"],
            "clients/wuhan-tutoring/references/article/6865ebf8000000001e004b42-01-初三数学二次函数避坑点.md",
        )
        self.assertEqual(
            note["image_path"],
            "clients/wuhan-tutoring/references/images/6865ebf8000000001e004b42-01-初三数学二次函数避坑点.png",
        )

    def test_build_source_index_marks_partial_for_profile_card_only_collection(self) -> None:
        profile_results = [
            {
                "source_profile_url": "https://www.xiaohongshu.com/user/profile/a",
                "fetch_state": "partial",
                "collected_via": "chrome_cdp_profile_cards",
                "notes": [
                    {
                        "title": "A",
                        "access_level": "profile_card",
                    }
                ],
            },
            {
                "source_profile_url": "https://www.xiaohongshu.com/user/profile/b",
                "fetch_state": "blocked",
                "blocked_reason": "login_required",
                "notes": [],
            },
        ]
        notes = [
            {
                "title": "A",
                "source_profile_url": "https://www.xiaohongshu.com/user/profile/a",
                "access_level": "profile_card",
            }
        ]

        index = build_source_index(
            [
                "https://www.xiaohongshu.com/user/profile/a",
                "https://www.xiaohongshu.com/user/profile/b",
            ],
            profile_results,
            notes,
            "20260407-150000",
        )

        self.assertEqual(index["fetch_state"], "partial")
        self.assertEqual(index["updated_at"], "20260407-150000")
        self.assertEqual(index["configured_profiles"][0], "https://www.xiaohongshu.com/user/profile/a")
        self.assertEqual(index["profiles"][1]["fetch_state"], "blocked")
        self.assertEqual(index["notes"][0]["title"], "A")

    def test_persist_note_record_writes_markdown_and_downloaded_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_root_dir = common.ROOT_DIR
            original_clients_dir = common.CLIENTS_DIR
            try:
                common.ROOT_DIR = Path(temp_dir)
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                note = build_note_record(
                    "wuhan-tutoring",
                    {
                        "title": "初三数学二次函数避坑点",
                        "author": "武汉补习班",
                        "source_profile_url": "https://www.xiaohongshu.com/user/profile/abc",
                        "collected_via": "chrome_cdp_profile_cards",
                        "access_level": "profile_card",
                        "note_url": None,
                        "image_url": "https://ci.xiaohongshu.com/cover.jpg",
                    },
                    1,
                )

                persisted = persist_note_record(
                    note,
                    downloader=lambda url: b"fake-image-bytes",
                )

                article_path = Path(temp_dir) / persisted["article_snapshot_path"]
                image_path = Path(temp_dir) / persisted["image_path"]

                self.assertTrue(article_path.exists())
                self.assertTrue(image_path.exists())
                self.assertEqual(image_path.read_bytes(), b"fake-image-bytes")
                self.assertEqual(persisted["image_downloaded"], True)
            finally:
                common.ROOT_DIR = original_root_dir
                common.CLIENTS_DIR = original_clients_dir

    def test_collect_materials_dry_run_returns_plan_without_writing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            original_root_dir = common.ROOT_DIR
            try:
                common.ROOT_DIR = Path(temp_dir)
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                workflow_path = common.get_client_workflow_path("wuhan-tutoring")
                workflow_path.parent.mkdir(parents=True, exist_ok=True)
                workflow_path.write_text(
                    yaml.safe_dump(
                        {
                            "materials": {
                                "source_profiles": [
                                    "https://www.xiaohongshu.com/user/profile/a",
                                ]
                            }
                        },
                        allow_unicode=True,
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )

                def fake_collector(profile_url: str, limit_notes: int, cdp_url: str) -> dict[str, object]:
                    self.assertEqual(limit_notes, 2)
                    return {
                        "source_profile_url": profile_url,
                        "fetch_state": "partial",
                        "notes": [
                            {
                                "title": "初三数学二次函数避坑点",
                                "author": "武汉补习班",
                                "source_profile_url": profile_url,
                                "collected_via": "chrome_cdp_profile_cards",
                                "access_level": "profile_card",
                                "note_url": None,
                                "image_url": "https://ci.xiaohongshu.com/cover.jpg",
                            }
                        ],
                    }

                with patch("common.timestamp", return_value="20260407-150000"):
                    result = collect_materials(
                        client_slug="wuhan-tutoring",
                        limit_notes=2,
                        dry_run=True,
                        collector=fake_collector,
                        cdp_probe=lambda _url: True,
                    )

                self.assertTrue(result["dry_run"])
                self.assertEqual(result["fetch_state"], "partial")
                self.assertEqual(len(result["notes"]), 1)
                self.assertFalse(
                    (Path(temp_dir) / "clients" / "wuhan-tutoring" / "references" / "article").exists()
                )
                self.assertFalse(
                    (Path(temp_dir) / "clients" / "wuhan-tutoring" / "references" / "source-index.json").exists()
                )
            finally:
                common.ROOT_DIR = original_root_dir
                common.CLIENTS_DIR = original_clients_dir

    def test_collect_materials_reports_blocked_when_cdp_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_clients_dir = common.CLIENTS_DIR
            original_root_dir = common.ROOT_DIR
            try:
                common.ROOT_DIR = Path(temp_dir)
                common.CLIENTS_DIR = Path(temp_dir) / "clients"
                workflow_path = common.get_client_workflow_path("wuhan-tutoring")
                workflow_path.parent.mkdir(parents=True, exist_ok=True)
                workflow_path.write_text(
                    yaml.safe_dump(
                        {
                            "materials": {
                                "source_profiles": [
                                    "https://www.xiaohongshu.com/user/profile/a",
                                ]
                            }
                        },
                        allow_unicode=True,
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )

                with patch("common.timestamp", return_value="20260407-150000"):
                    result = collect_materials(
                        client_slug="wuhan-tutoring",
                        limit_notes=2,
                        dry_run=False,
                        cdp_probe=lambda _url: False,
                    )

                self.assertEqual(result["fetch_state"], "blocked")
                self.assertEqual(result["profiles"][0]["blocked_reason"], "cdp_unavailable")
                self.assertFalse(
                    (Path(temp_dir) / "clients" / "wuhan-tutoring" / "references" / "source-index.json").exists()
                )
            finally:
                common.ROOT_DIR = original_root_dir
                common.CLIENTS_DIR = original_clients_dir


if __name__ == "__main__":
    unittest.main()
