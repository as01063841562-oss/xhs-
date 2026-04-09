from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from web.auth import (
    clear_session,
    load_access_config,
    require_role,
    role_for_token,
    session_account_key,
    session_role,
    set_session_account_key,
    set_session_role,
)
from web.job_runner import latest_job_for_task, start_job
from web.repository import DEFAULT_ACCOUNT_KEY, get_task
from web.services import create_web_task, list_synced_tasks, run_task_action, set_materials_gate, sync_task_from_runtime
from xhs_customer_state import load_materials_ready

CLIENT_SLUG = "wuhan-tutoring"
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def build_app() -> FastAPI:
    access = load_access_config(CLIENT_SLUG)
    app = FastAPI(title="Wuhan Tutoring Workflow")
    app.add_middleware(SessionMiddleware, secret_key=access["secret_key"])
    app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")

    def render(request: Request, template: str, **context):
        flash = request.session.pop("flash", None)
        return TEMPLATES.TemplateResponse(
            request=request,
            name=template,
            context={**context, "flash": flash},
        )

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        role = session_role(request)
        if role == "ops":
            return RedirectResponse("/ops", status_code=303)
        if role == "client":
            return RedirectResponse("/client", status_code=303)
        return RedirectResponse("/login", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, message: str | None = None):
        return render(request, "login.html", title="进入武汉教培 Workflow", message=message)

    @app.get("/magic-link")
    def magic_link(request: Request, token: str):
        role = role_for_token(token, CLIENT_SLUG)
        if not role:
            return RedirectResponse("/login?message=invalid-link", status_code=303)
        set_session_role(request, role, CLIENT_SLUG)
        return RedirectResponse("/ops" if role == "ops" else "/client", status_code=303)

    @app.get("/logout")
    def logout(request: Request):
        clear_session(request)
        return RedirectResponse("/login?message=logged-out", status_code=303)

    @app.get("/ops", response_class=HTMLResponse)
    def ops_dashboard(request: Request, account_key: str | None = None):
        require_role(request, {"ops"})
        if account_key is not None:
            set_session_account_key(request, account_key)
        active_account_key = session_account_key(request)
        tasks = list_synced_tasks(CLIENT_SLUG, account_key=active_account_key)
        return render(
            request,
            "ops.html",
            title="武汉教培运营看板",
            tasks=tasks,
            account_key=active_account_key,
            materials_ready=bool(load_materials_ready(CLIENT_SLUG)),
        )

    @app.get("/client", response_class=HTMLResponse)
    def client_dashboard(request: Request, account_key: str | None = None):
        require_role(request, {"client", "ops"})
        if account_key is not None:
            set_session_account_key(request, account_key)
        active_account_key = session_account_key(request)
        tasks = list_synced_tasks(CLIENT_SLUG, account_key=active_account_key)
        return render(request, "client.html", title="武汉教培客户视图", tasks=tasks, account_key=active_account_key)

    @app.post("/tasks")
    def create_task_route(
        request: Request,
        title: str = Form(...),
        topic: str = Form(...),
        audience: str = Form("武汉家长"),
        account_key: str | None = Form(None),
    ):
        role = require_role(request, {"client", "ops"})
        active_account_key = str(account_key or session_account_key(request)).strip() or DEFAULT_ACCOUNT_KEY
        set_session_account_key(request, active_account_key)
        task = create_web_task(
            CLIENT_SLUG,
            title=title,
            topic=topic,
            audience=audience,
            created_by_role=role,
            account_key=active_account_key,
        )
        request.session["flash"] = f"任务已创建：{task['title']}"
        return RedirectResponse(f"/tasks/{task['task_id']}", status_code=303)

    @app.get("/tasks/{task_id}", response_class=HTMLResponse)
    def task_detail(request: Request, task_id: str):
        require_role(request, {"client", "ops"})
        task = sync_task_from_runtime(CLIENT_SLUG, get_task(CLIENT_SLUG, task_id))
        latest_job = latest_job_for_task(CLIENT_SLUG, task_id)
        return render(request, "task_detail.html", title="任务详情", task=task, latest_job=latest_job)

    @app.post("/tasks/{task_id}/actions/{action}")
    def task_action(
        request: Request,
        task_id: str,
        action: str,
        topic_title: str = Form(""),
        message: str = Form(""),
    ):
        role = require_role(request, {"client", "ops"})
        payload = {}
        if topic_title:
            payload["topic_title"] = topic_title
        if message:
            payload["message"] = message

        if action in {"sync"}:
            run_task_action(CLIENT_SLUG, task_id, action, payload, dry_run=False)
            request.session["flash"] = f"已同步任务 {task_id}"
            return RedirectResponse(f"/tasks/{task_id}", status_code=303)

        if role == "client" and action == "request-change":
            run_task_action(CLIENT_SLUG, task_id, action, payload, dry_run=False)
            request.session["flash"] = "修改请求已提交给运营侧"
            return RedirectResponse(f"/tasks/{task_id}", status_code=303)

        allowed_ops_actions = {
            "generate-topic",
            "select-topic",
            "confirm-current",
            "generate-cover",
            "generate-graphics",
            "request-change",
        }
        if role != "ops" and action in allowed_ops_actions:
            request.session["flash"] = "当前角色无权限执行该操作"
            return RedirectResponse(f"/tasks/{task_id}", status_code=303)

        job = start_job(
            CLIENT_SLUG,
            task_id,
            action,
            run_task_action,
            CLIENT_SLUG,
            task_id,
            action,
            payload,
            False,
        )
        request.session["flash"] = f"已启动后台作业：{job['action']}"
        return RedirectResponse(f"/tasks/{task_id}", status_code=303)

    @app.post("/ops/materials-gate")
    def update_materials_gate(request: Request, materials_ready: str = Form(...)):
        require_role(request, {"ops"})
        ready = materials_ready.lower() == "true"
        set_materials_gate(CLIENT_SLUG, ready)
        request.session["flash"] = f"已将生产闸门切换为 {'ready' if ready else 'blocked'}"
        return RedirectResponse("/ops", status_code=303)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "client": CLIENT_SLUG}

    return app


app = build_app()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Wuhan workflow web MVP.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8047)
    args = parser.parse_args(argv)

    access = load_access_config(CLIENT_SLUG)
    print(f"Ops link:    http://{args.host}:{args.port}/magic-link?token={access['ops_token']}")
    print(f"Client link: http://{args.host}:{args.port}/magic-link?token={access['client_token']}")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
