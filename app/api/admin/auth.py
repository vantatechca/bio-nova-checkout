from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.deps import Config
from app.errors import Unauthorized
from app.security import AdminTokens, client_ip, constant_time_equals, login_limiter

router = APIRouter(prefix="/api/admin", tags=["admin: auth"])


class LoginIn(BaseModel):
    password: str = ""


@router.post("/login")
def login(data: LoginIn, request: Request, config: Config) -> dict[str, str]:
    ip = client_ip(request)
    login_limiter.check(ip)
    if not constant_time_equals(data.password, request.app.state.admin_password):
        login_limiter.record_failure(ip)
        raise Unauthorized("Incorrect password")
    login_limiter.reset(ip)
    return {"token": AdminTokens.issue(config.secret)}


@router.post("/logout")
def logout() -> dict[str, bool]:
    # Tokens are stateless and expire on their own; the browser simply discards its copy.
    return {"ok": True}
