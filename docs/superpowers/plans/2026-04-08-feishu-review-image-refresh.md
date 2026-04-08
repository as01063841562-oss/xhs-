# Feishu Review Image Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Feishu review card's old `modify / rewrite` image-side actions with `refresh_cover / refresh_graphics`, and make the card payload, bridge resume command, and local resume flow agree end-to-end.

**Architecture:** Keep the existing Feishu review flow in `scripts/xhs_feishu_flow.py` as its own lane, but change its semantics so `refresh_cover` and `refresh_graphics` only regenerate images and never reopen the revision-notes flow. Update the OpenClaw Lark bridge helper that synthesizes `resume_command` so the new buttons produce deterministic follow-up commands instead of relying on model inference.

**Tech Stack:** Python 3, unittest, existing Feishu review scripts, Node/JS bridge helper in `.openclaw/extensions/openclaw-lark`, existing dry-run smoke commands.

---

## File Structure

### New Files

- Create: `tests/test_feishu_client.py`
- Create: `tests/test_xhs_feishu_flow.py`

### Modified Files

- Modify: `scripts/feishu_client.py`
- Modify: `scripts/xhs_feishu_flow.py`
- Modify: `SKILL.md`
- Modify: `docs/troubleshooting.md`
- Modify: `/Users/lmsx/.openclaw/extensions/openclaw-lark/src/tools/auto-auth.js`
- Modify: `/Users/lmsx/.openclaw/extensions/openclaw-lark/src/tools/auto-auth.d.ts`

## Task 1: Change Review Card Button Payloads

**Files:**
- Create: `tests/test_feishu_client.py`
- Modify: `scripts/feishu_client.py`

- [ ] **Step 1: Write the failing button-payload test**

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from feishu_client import FeishuClient


class FeishuClientReviewCardTest(unittest.TestCase):
    def test_send_review_card_uses_refresh_decisions(self) -> None:
        captured = {}

        def fake_send(self, msg_type, content):
            captured["msg_type"] = msg_type
            captured["content"] = content
            return "om_test"

        with patch.object(FeishuClient, "_send_message", fake_send):
            client = FeishuClient.__new__(FeishuClient)
            client.send_review_card(
                image_key=["img_a", "img_b"],
                title="标题",
                content="内容",
                tags="#标签",
                note_id="note-1",
            )

        card = captured["content"]
        actions = card["elements"][-1]["actions"]
        self.assertEqual(captured["msg_type"], "interactive")
        self.assertEqual(actions[0]["value"]["decision"], "approve")
        self.assertEqual(actions[1]["value"]["decision"], "refresh_cover")
        self.assertEqual(actions[2]["value"]["decision"], "refresh_graphics")
        self.assertEqual(actions[1]["text"]["content"], "刷新封面图")
        self.assertEqual(actions[2]["text"]["content"], "刷新内容配图")
```

- [ ] **Step 2: Run the new test to verify it fails for the old button contract**

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python -m unittest tests.test_feishu_client.FeishuClientReviewCardTest.test_send_review_card_uses_refresh_decisions -v
```

Expected:

- FAIL because the card still emits `modify` / `rewrite` decisions and old button labels.

- [ ] **Step 3: Update `send_review_card()` to emit the new action contract**

```python
{
    "tag": "button",
    "text": {"tag": "plain_text", "content": "刷新封面图"},
    "type": "default",
    "value": {
        "action": "xhs_review",
        "decision": "refresh_cover",
        "note_id": note_id,
    },
},
{
    "tag": "button",
    "text": {"tag": "plain_text", "content": "刷新内容配图"},
    "type": "default",
    "value": {
        "action": "xhs_review",
        "decision": "refresh_graphics",
        "note_id": note_id,
    },
},
```

- [ ] **Step 4: Re-run the test to verify the card contract is green**

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python -m unittest tests.test_feishu_client -v
```

Expected:

- PASS for the new review-card payload test.

## Task 2: Add `refresh_cover` / `refresh_graphics` Resume Semantics

**Files:**
- Create: `tests/test_xhs_feishu_flow.py`
- Modify: `scripts/xhs_feishu_flow.py`

- [ ] **Step 1: Write failing tests for image-refresh resume behavior**

```python
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

import xhs_feishu_flow


class XhsFeishuFlowRefreshTest(unittest.TestCase):
    def test_resume_refresh_cover_keeps_payload_and_sends_new_review_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            state = {
                "payload": {"cover_title": "标题", "hashtags": ["武汉"], "variants": [{"title": "v1", "angle": "a", "body": "b"}]},
                "topic": "主题",
                "audience": "家长",
                "dry_run": True,
                "skip_image": False,
                "image_keys": ["img_old_1", "img_old_2"],
                "image_key": "img_old_1",
                "current_review_message_id": "om_old",
                "note_id": "note-1",
                "revision_count": 0,
            }

            with patch("xhs_feishu_flow.load_review_state", return_value=(run_dir, state)), \
                 patch("xhs_feishu_flow.generate_slide_images", return_value=[run_dir / "cover-new.png"]), \
                 patch("xhs_feishu_flow.upload_slide_images", return_value=["img_new"]), \
                 patch("xhs_feishu_flow.save_review_state"), \
                 patch("xhs_feishu_flow._save_result"), \
                 patch("xhs_feishu_flow.FeishuClient") as mock_client:
                mock_client.return_value.send_review_card.return_value = "om_new"
                result = xhs_feishu_flow.resume_review_action("refresh_cover", "om_old", dry_run=False)

            self.assertEqual(result["status"], "waiting_review")
            self.assertEqual(state["payload"]["cover_title"], "标题")
            self.assertEqual(state["current_review_message_id"], "om_new")
            self.assertEqual(state["cover_refresh_count"], 1)

    def test_resume_refresh_graphics_keeps_payload_and_sends_multi_image_review_card(self) -> None:
        ...

    def test_resume_refresh_actions_reject_missing_or_stale_message_ids_using_existing_guard(self) -> None:
        ...
```

- [ ] **Step 2: Run the new flow tests to verify they fail because the actions are unsupported**

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python -m unittest tests.test_xhs_feishu_flow -v
```

Expected:

- FAIL with unsupported action handling or missing refresh-specific behavior.

- [ ] **Step 3: Extend the CLI and resume flow with the new actions**

Implement the smallest behavior change that satisfies the tests:

```python
parser.add_argument(
    "--action",
    choices=["approve", "modify", "rewrite", "refresh_cover", "refresh_graphics"],
    default=None,
    help="resume 模式下的卡片动作",
)
```

```python
if action == "refresh_cover":
    # keep payload, regenerate only cover-facing image set, upload, resend review card
    ...

if action == "refresh_graphics":
    # keep payload, regenerate only graphics image set, upload, resend review card
    ...
```

State updates must include:

```python
state["review_action_mode"] = "image_refresh"
state["cover_refresh_count"] = int(state.get("cover_refresh_count", 0)) + 1
```

or:

```python
state["graphics_refresh_count"] = int(state.get("graphics_refresh_count", 0)) + 1
```

Do not call `send_revision_request()` from the new branches.

- [ ] **Step 4: Re-run the focused flow tests, then run a dry-run CLI smoke command**

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python -m unittest tests.test_xhs_feishu_flow -v
```

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python scripts/xhs_feishu_flow.py --topic "测试" --mode draft --dry-run --json
```

Expected:

- Flow tests PASS.
- Draft dry-run still returns a review-card result.

- [ ] **Step 5: Add a backwards-compatibility test for old actions**

```python
def test_resume_modify_still_uses_revision_lane(self) -> None:
    ...
```

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python -m unittest tests.test_xhs_feishu_flow -v
```

Expected:

- PASS, with legacy `modify / rewrite` behavior still accepted.

## Task 3: Update OpenClaw Bridge `resume_command`

**Files:**
- Modify: `/Users/lmsx/.openclaw/extensions/openclaw-lark/src/tools/auto-auth.js`
- Modify: `/Users/lmsx/.openclaw/extensions/openclaw-lark/src/tools/auto-auth.d.ts`

- [ ] **Step 1: Narrow the bridge change to `buildXhsReviewSyntheticText()`**

Before editing, inspect only this helper and its call site:

```javascript
function buildXhsReviewSyntheticText(action, messageId, noteId, options = {}) {
  ...
}
```

- [ ] **Step 2: Change the helper so refresh actions generate direct resume commands**

Implement the minimal explicit branching:

```javascript
if (action === 'refresh_cover' || action === 'refresh_graphics') {
  return `cd "${XHS_FLOW_WORKSPACE}" && "${XHS_FLOW_PYTHON}" scripts/xhs_feishu_flow.py --mode resume --action ${action} --message-id "${messageId}"`;
}
```

Keep the old `approve / modify / rewrite` branches intact for compatibility.

- [ ] **Step 3: Update the bridge type/docs comment to describe the new card actions**

Change references like:

```ts
"通过 / 修改 / 重写"
```

to language that includes:

```ts
"通过 / 刷新封面图 / 刷新内容配图"
```

and explicitly mention that old `modify / rewrite` callbacks are still tolerated for historical cards.

- [ ] **Step 4: Run syntax-only verification for the bridge files**

Run:

```bash
node --check /Users/lmsx/.openclaw/extensions/openclaw-lark/src/tools/auto-auth.js
```

Expected:

- No syntax errors.

## Task 4: Update Project Docs And Run End-to-End Verification

**Files:**
- Modify: `SKILL.md`
- Modify: `docs/troubleshooting.md`
- Modify: `scripts/smoke_test.py` (only if needed to keep documented smoke paths current)

- [ ] **Step 1: Update user-facing docs to reflect the new button language**

Replace outdated text such as:

```md
✅通过 / ✏️修改 / ❌重写
```

with:

```md
✅通过 / 刷新封面图 / 刷新内容配图
```

Also update the callback/resume examples so they mention `refresh_cover` and `refresh_graphics`.

- [ ] **Step 2: Run the repo-side test suite that covers the touched surfaces**

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python -m unittest tests.test_feishu_client tests.test_xhs_feishu_flow -v
```

Expected:

- PASS for all new review-card and resume-flow tests.

- [ ] **Step 3: Run the existing core workflow regression suite**

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python -m unittest tests.test_xhs_customer_state tests.test_xhs_feedback_parser tests.test_xhs_customer_router tests.test_xhs_material_collector tests.test_xhs_style_analyzer -v
```

Expected:

- PASS, proving the Feishu review changes did not break the Wuhan customer router lane.

- [ ] **Step 4: Run a dry-run resume smoke for both new actions**

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python scripts/xhs_feishu_flow.py --mode resume --action refresh_cover --message-id om_demo --dry-run --json
```

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python scripts/xhs_feishu_flow.py --mode resume --action refresh_graphics --message-id om_demo --dry-run --json
```

Expected:

- Both commands produce deterministic image-refresh results or a clear stale/missing-state error that matches the documented contract.

## Self-Review

### Spec coverage

- New card buttons and payload contract: covered in Task 1.
- New `resume_command` bridge behavior: covered in Task 3.
- New `refresh_cover / refresh_graphics` runtime semantics: covered in Task 2.
- Legacy compatibility for historical cards: covered in Tasks 2 and 3.
- Docs and smoke validation: covered in Task 4.

### Placeholder scan

- No `TODO`, `TBD`, or “implement later” placeholders remain.
- Every task names exact files and concrete verification commands.

### Type consistency

- New action names are consistently `refresh_cover` and `refresh_graphics`.
- Old actions remain `approve`, `modify`, and `rewrite` only for compatibility.
- `resume_command` and CLI `--action` values are aligned.
