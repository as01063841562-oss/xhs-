# Feishu Control Plane and Web Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Feishu the canonical control plane for the Wuhan workflow while keeping the web app as a read-through projection and rework surface, and reserve `account_key` for future multi-account control.

**Architecture:** Keep the file-backed workflow as the source of truth, let `scripts/xhs_customer_router.py` and `scripts/xhs_feishu_flow.py` continue to own runtime state, and make the web app hydrate a task projection from runtime files before showing or mutating anything. Introduce `account_key` at the task registry layer now so the first-phase schema can grow into multi-account control without rewriting the UI later.

**Tech Stack:** Python 3, FastAPI, Jinja2, unittest, existing file-backed workflow scripts, existing web task registry.

---

## File Structure

### New Files

- Create: `docs/superpowers/plans/2026-04-08-feishu-control-plane-web-projection.md`

### Modified Files

- Modify: `web/repository.py`
- Modify: `web/services.py`
- Modify: `web/app.py`
- Modify: `web/templates/ops.html`
- Modify: `web/templates/client.html`
- Modify: `web/templates/task_detail.html`
- Modify: `tests/test_web_repository.py`
- Modify: `tests/test_web_services.py`
- Modify: `tests/test_web_app.py`
- Modify: `README.md`

## Task 1: Add `account_key` To The Web Task Model

**Files:**
- Modify: `web/repository.py`
- Modify: `web/services.py`
- Modify: `web/app.py`
- Modify: `tests/test_web_repository.py`

- [ ] **Step 1: Write the failing repository test**

```python
def test_create_task_defaults_account_key(self) -> None:
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

            self.assertEqual(task["account_key"], "primary")
            self.assertEqual(get_task("wuhan-tutoring", task["task_id"])["account_key"], "primary")
        finally:
            common.CLIENTS_DIR = original_clients_dir
```

- [ ] **Step 2: Run the test and verify the old schema fails**

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python -m unittest tests.test_web_repository.WebRepositoryTest.test_create_task_defaults_account_key -v
```

Expected:

- FAIL because the task record does not yet include `account_key`.

- [ ] **Step 3: Add `account_key` to the repository and service signatures**

```python
DEFAULT_ACCOUNT_KEY = "primary"

def _new_task_record(..., account_key: str = DEFAULT_ACCOUNT_KEY) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "client_slug": client_slug,
        "account_key": account_key,
        ...
    }

def create_task(..., created_by_role: str, account_key: str = DEFAULT_ACCOUNT_KEY) -> dict[str, Any]:
    task = _new_task_record(client_slug, title, topic, audience, created_by_role, account_key=account_key)
    ...
```

```python
def create_web_task(
    client_slug: str,
    title: str,
    topic: str,
    audience: str,
    created_by_role: str,
    account_key: str = DEFAULT_ACCOUNT_KEY,
) -> dict[str, Any]:
    task = create_task(
        client_slug,
        title,
        topic,
        audience,
        created_by_role,
        account_key=account_key,
    )
    return sync_task_from_runtime(client_slug, task)
```

```python
DEFAULT_ACCOUNT_KEY = "primary"

@app.post("/tasks")
def create_task_route(...):
    ...
    task = create_web_task(
        CLIENT_SLUG,
        title=title,
        topic=topic,
        audience=audience,
        created_by_role=role,
        account_key=DEFAULT_ACCOUNT_KEY,
    )
```

- [ ] **Step 4: Re-run the focused tests to confirm the task model is stable**

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python -m unittest tests.test_web_repository tests.test_web_app -v
```

Expected:

- PASS for the new default-account-key test and the existing spoofed-role regression.

## Task 2: Make The Web UI Read Like A Projection, Not A Second Workflow Engine

**Files:**
- Modify: `web/services.py`
- Modify: `web/templates/ops.html`
- Modify: `web/templates/client.html`
- Modify: `web/templates/task_detail.html`
- Modify: `tests/test_web_services.py`

- [ ] **Step 1: Write the failing sync test that proves runtime wins over stale task fields**

```python
def test_sync_task_from_runtime_prefers_runtime_over_stale_task_fields(self) -> None:
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
                        "current_state": "state_2_cover",
                        "session_output_dir": str(Path(temp_dir) / "session-a"),
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

            self.assertEqual(synced["current_state"], "state_2_cover")
            self.assertEqual(synced["status"], "stale")
            self.assertEqual(synced["review_message_id"], "om_test")
            self.assertEqual(synced["runtime_status"], "waiting_review")
        finally:
            common.CLIENTS_DIR = original_clients_dir
```

- [ ] **Step 2: Run the test and verify the old projection logic is incomplete**

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python -m unittest tests.test_web_services.WebServicesTest.test_sync_task_from_runtime_prefers_runtime_over_stale_task_fields -v
```

Expected:

- FAIL until the projection path explicitly overwrites stale task fields from runtime state.

- [ ] **Step 3: Tighten the projection helper and surface the account key in the UI**

```python
def sync_task_from_runtime(client_slug: str, task: dict[str, Any]) -> dict[str, Any]:
    synced = deepcopy(task)
    state = load_state(client_slug, task["open_id"])
    synced["current_state"] = state.get("current_state", synced.get("current_state"))
    synced["materials_ready"] = state.get("materials_ready", synced.get("materials_ready"))
    synced["session_output_dir"] = state.get("session_output_dir")
    synced["confirmed"] = state.get("confirmed", {})
    synced["drafts"] = state.get("drafts", {})
    synced["account_key"] = synced.get("account_key") or "primary"
    ...
```

```html
<span>账号: {{ task.account_key or "primary" }}</span>
```

Add the same `account_key` marker to:

- the ops task cards
- the client task cards
- the task detail summary

- [ ] **Step 4: Re-run the web-service tests and verify the UI still renders**

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python -m unittest tests.test_web_services tests.test_web_app -v
```

Expected:

- PASS for the projection test.
- PASS for the existing web app regression.

## Task 3: Document The Boundary And Verify The Whole Suite

**Files:**
- Modify: `README.md`
- Modify: `docs/troubleshooting.md` if the runtime/projection boundary needs an operator note

- [ ] **Step 1: Add a short operator note that states the control-plane rule**

```markdown
Feishu is the canonical control plane for review and confirmation. The web app is a projection layer for rework, visual inspection, and operator convenience; it reads runtime state back in before showing or mutating anything. If runtime state and web task rows disagree, runtime wins.
```

- [ ] **Step 2: Run the full workflow and web test suite**

Run:

```bash
cd /Users/lmsx/.config/superpowers/worktrees/edu-media-openclaw/codex-wuhan-xhs-workflow && .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

Expected:

- PASS across the full suite.

- [ ] **Step 3: Commit the implementation**

```bash
git add web/repository.py web/services.py web/app.py web/templates/ops.html web/templates/client.html web/templates/task_detail.html tests/test_web_repository.py tests/test_web_services.py tests/test_web_app.py README.md docs/troubleshooting.md
git commit -m "feat: make feishu the control plane"
```

## Self-Review

### Spec coverage

- Feishu as canonical control plane: covered by Task 2 and Task 3.
- Web as projection and rework surface: covered by Task 2.
- Runtime state wins over stale task rows: covered by Task 2.
- Future multi-account extension point: covered by Task 1.
- Existing single-client workflow compatibility: covered by Task 1 and Task 3.

### Placeholder scan

- No `TBD`, `TODO`, or vague “handle edge cases” steps remain.
- Every code-changing step includes the actual file and code shape involved.

### Type consistency

- `account_key` is introduced first in `web/repository.py`, then passed through `web/services.py` and `web/app.py`, and finally rendered in the templates.
- The sync test uses the same `open_id` and runtime file paths as the existing web-service tests, so the new assertions match the current file layout.

