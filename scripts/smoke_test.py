#!/usr/bin/env python3
"""首期工程冒烟测试。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def run_json(command: list[str]) -> dict:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    text = completed.stdout.strip()
    marker = "__JSON_RESULT__"
    if marker in text:
        return json.loads(text.split(marker, 1)[1].strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{[\s\S]*\})\s*$", text)
        if not match:
            raise
        return json.loads(match.group(1))


def assert_exists(path_str: str) -> None:
    if not Path(path_str).exists():
        raise AssertionError(f"文件不存在: {path_str}")


def main() -> None:
    python_bin = sys.executable

    env_result = run_json([python_bin, str(SCRIPT_DIR / "check_env.py"), "--json"])
    prepare_result = run_json(
        [
            python_bin,
            str(SCRIPT_DIR / "wechat_generate.py"),
            "--json",
            "prepare",
            "--topic",
            "AI 自动化如何提升教育自媒体效率",
            "--audience",
            "教育行业创始人和运营负责人",
            "--dry-run",
        ]
    )
    produce_result = run_json(
        [
            python_bin,
            str(SCRIPT_DIR / "wechat_generate.py"),
            "--json",
            "produce",
            "--task-dir",
            prepare_result["task_dir"],
            "--outline-approved",
            "--publish-draft",
            "--dry-run",
        ]
    )
    xhs_result = run_json(
        [
            python_bin,
            str(SCRIPT_DIR / "xhs_generate.py"),
            "--json",
            "--topic",
            "教培机构如何用 AI 节省内容运营时间",
            "--audience",
            "校长和新媒体负责人",
            "--dry-run",
            "--render-cover",
        ]
    )
    xhs_flow_draft = run_json(
        [
            python_bin,
            str(SCRIPT_DIR / "xhs_feishu_flow.py"),
            "--json",
            "--topic",
            "卡片修改流程测试",
            "--audience",
            "教育行业运营负责人",
            "--dry-run",
            "--mode",
            "draft",
        ]
    )
    xhs_flow_edit = run_json(
        [
            python_bin,
            str(SCRIPT_DIR / "xhs_feishu_flow.py"),
            "--json",
            "--mode",
            "request-edit",
            "--action",
            "modify",
            "--message-id",
            xhs_flow_draft["steps"]["review_card"],
            "--dry-run",
        ]
    )
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as handle:
        json.dump(
            {
                "revision_notes": "封面标题更聚焦，正文前两段更口语化。",
                "revision_scope": "title/body",
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )
        revision_notes_file = handle.name
    xhs_flow_resume = run_json(
        [
            python_bin,
            str(SCRIPT_DIR / "xhs_feishu_flow.py"),
            "--json",
            "--mode",
            "resume",
            "--action",
            "modify",
            "--message-id",
            xhs_flow_edit["steps"]["revision_request_card"],
            "--revision-notes-file",
            revision_notes_file,
            "--dry-run",
        ]
    )

    for key in ("task_file", "outline_file"):
        assert_exists(prepare_result[key])
    for key in ("article_file", "image_prompts", "article_html", "draft_push_result"):
        assert_exists(produce_result[key])
    for key in (
        "note_variants",
        "hashtags",
        "cover_title",
        "cover_prompt",
        "publish_checklist",
        "cover_image",
    ):
        assert_exists(xhs_result[key])
    for key in ("task_dir", "steps"):
        if key not in xhs_flow_draft:
            raise AssertionError(f"缺少字段: {key}")
    for key in ("revision_request_card",):
        if key not in xhs_flow_edit["steps"]:
            raise AssertionError(f"缺少字段: {key}")
    for key in ("review_card",):
        if key not in xhs_flow_resume["steps"]:
            raise AssertionError(f"缺少字段: {key}")

    summary = {
        "status": "passed",
        "env": {
            "openclaw": env_result["commands"]["openclaw"],
            "requests": env_result["python_modules"]["requests"],
        },
        "wechat": produce_result,
        "xhs": xhs_result,
        "xhs_flow": {
            "draft": xhs_flow_draft,
            "edit": xhs_flow_edit,
            "resume": xhs_flow_resume,
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
