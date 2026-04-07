from __future__ import annotations

import sys
from pathlib import Path

from fastapi import HTTPException, Request

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from web.repository import ensure_access_config

CLIENT_SLUG = "wuhan-tutoring"


def load_access_config(client_slug: str = CLIENT_SLUG) -> dict[str, str]:
    return ensure_access_config(client_slug)


def role_for_token(token: str, client_slug: str = CLIENT_SLUG) -> str | None:
    access = load_access_config(client_slug)
    if token == access["ops_token"]:
        return "ops"
    if token == access["client_token"]:
        return "client"
    return None


def set_session_role(request: Request, role: str, client_slug: str = CLIENT_SLUG) -> None:
    request.session["role"] = role
    request.session["client_slug"] = client_slug


def clear_session(request: Request) -> None:
    request.session.clear()


def session_role(request: Request) -> str | None:
    return request.session.get("role")


def require_role(request: Request, allowed: set[str]) -> str:
    role = session_role(request)
    if role not in allowed:
        raise HTTPException(status_code=403, detail="forbidden")
    return str(role)
