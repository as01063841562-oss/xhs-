# Wuhan Workflow Web Product Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable first-phase web product for the Wuhan tutoring workflow using the existing script and file-state system.

**Architecture:** Add a small FastAPI + Jinja web layer that wraps the existing router, collector, analyzer, and Feishu-review outputs. Keep the current file-based workflow as the source of truth and avoid platform-level abstractions.

**Tech Stack:** Python 3, FastAPI, Jinja2, HTMX, stdlib `subprocess` / `threading`, existing workflow scripts.

---

## File Structure

### New Files

- Create: `docs/superpowers/specs/2026-04-07-wuhan-workflow-web-product-design.md`
- Create: `docs/superpowers/plans/2026-04-07-wuhan-workflow-web-product.md`
- Create: `web/app.py`
- Create: `web/auth.py`
- Create: `web/job_runner.py`
- Create: `web/repository.py`
- Create: `web/services.py`
- Create: `web/templates/base.html`
- Create: `web/templates/ops.html`
- Create: `web/templates/client.html`
- Create: `web/templates/task_detail.html`
- Create: `web/templates/login.html`
- Create: `web/static/app.css`
- Create: `tests/test_web_repository.py`
- Create: `tests/test_web_services.py`

### Modified Files

- Modify: `requirements.txt`
- Modify: `README.md`

## Task 1: Add Web Dependencies And Task Storage

**Files:**
- Modify: `requirements.txt`
- Create: `web/repository.py`
- Create: `tests/test_web_repository.py`

- [ ] Add `fastapi`, `uvicorn`, `jinja2`, and `itsdangerous` to `requirements.txt`.
- [ ] Create a task repository that stores tasks in `clients/wuhan-tutoring/state/web_tasks.json`.
- [ ] Add helpers to create tasks, list tasks, read one task, and update task fields.
- [ ] Add tests covering task creation and update round-trip.

## Task 2: Add Magic-Link Style Auth

**Files:**
- Create: `web/auth.py`
- Create: `web/templates/login.html`

- [ ] Create a lightweight access-token store in `clients/wuhan-tutoring/state/web_access.json`.
- [ ] Ensure one `ops` token and one `client` token exist.
- [ ] Implement `GET /magic-link?token=...` to establish a role-based session cookie.
- [ ] Implement a simple login/failure page for invalid tokens.

## Task 3: Add Web Service Adapters Around Existing Workflow Code

**Files:**
- Create: `web/services.py`
- Create: `tests/test_web_services.py`

- [ ] Wrap `xhs_customer_router.route_message()` so web actions can call it by task id.
- [ ] Add helpers that read `review_state.json`, `result.json`, and customer state files into a task view model.
- [ ] Add a helper to synthesize an `open_id` for web-created tasks.
- [ ] Add tests covering task-to-router payload mapping and file-state summary extraction.

## Task 4: Add Background Job Runner

**Files:**
- Create: `web/job_runner.py`

- [ ] Implement a minimal in-process background job runner using threads.
- [ ] Persist job status to `clients/wuhan-tutoring/state/web_jobs.json`.
- [ ] Support running router actions and long-running scripts without blocking HTTP requests.

## Task 5: Build Ops And Client Pages

**Files:**
- Create: `web/templates/base.html`
- Create: `web/templates/ops.html`
- Create: `web/templates/client.html`
- Create: `web/templates/task_detail.html`
- Create: `web/static/app.css`
- Create: `web/app.py`

- [ ] Build `/ops` showing all tasks, current stage, job status, and action buttons.
- [ ] Build `/client` showing only customer-facing tasks and customer action buttons.
- [ ] Build `/tasks/{task_id}` with stage timeline, current artifacts, and recent actions.
- [ ] Use server-rendered HTML and HTMX form posts for partial refreshes.

## Task 6: Wire First-Phase Actions

**Files:**
- Modify: `web/app.py`
- Modify: `web/services.py`

- [ ] Add `POST /tasks` to create a new task.
- [ ] Add ops actions for generate-topic, generate-copy, generate-cover, generate-graphics.
- [ ] Add shared actions for confirm-current-stage and request-change.
- [ ] Add a rerun-current-stage action that records the request and starts a job.
- [ ] Show Feishu review card ids and current review state when present.

## Task 7: Document And Verify The Web Product

**Files:**
- Modify: `README.md`

- [ ] Document how to install dependencies and run the web app.
- [ ] Document how to obtain the ops/client magic links.
- [ ] Run the new repository/service tests.
- [ ] Run the existing workflow test suite.
- [ ] Launch the app locally and verify `/ops`, `/client`, and `/tasks/{task_id}` render.

## Self-Review

### Spec coverage

- Single-customer Wuhan web product: covered.
- Ops/client split: covered.
- Magic-link style access: covered.
- Existing scripts remain the generation engine: covered.
- Working task board and detail pages: covered.

### Placeholder scan

- No placeholder tasks remain.
- All files and routes are explicit.

### Type consistency

- Tasks remain file-backed.
- Router remains the stage transition engine.
- Feishu remains an external notification/review channel, not replaced in phase 1.
