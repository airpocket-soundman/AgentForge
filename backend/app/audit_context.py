"""Request and actor context attached to audit log writes.

The control plane writes audit entries from many service modules. ContextVars
let request/auth metadata follow the current request without threading user
details through every function signature.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditRequestContext:
    request_id: str
    method: str
    path: str
    client: str | None
    user_agent: str | None
    origin: str | None
    referer: str | None


@dataclass(frozen=True)
class AuditActorContext:
    uid: str
    email: str
    is_admin: bool
    is_guest: bool


_request_ctx: ContextVar[AuditRequestContext | None] = ContextVar("audit_request_ctx", default=None)
_actor_ctx: ContextVar[AuditActorContext | None] = ContextVar("audit_actor_ctx", default=None)


def set_request_context(
    *,
    request_id: str,
    method: str,
    path: str,
    client: str | None,
    user_agent: str | None,
    origin: str | None,
    referer: str | None,
) -> Token[AuditRequestContext | None]:
    return _request_ctx.set(
        AuditRequestContext(
            request_id=request_id,
            method=method,
            path=path,
            client=client,
            user_agent=user_agent,
            origin=origin,
            referer=referer,
        )
    )


def reset_request_context(token: Token[AuditRequestContext | None]) -> None:
    _request_ctx.reset(token)


def clear_actor_context() -> Token[AuditActorContext | None]:
    return _actor_ctx.set(None)


def set_actor_context(*, uid: str, email: str, is_admin: bool, is_guest: bool) -> Token[AuditActorContext | None]:
    return _actor_ctx.set(
        AuditActorContext(uid=uid, email=email, is_admin=is_admin, is_guest=is_guest)
    )


def reset_actor_context(token: Token[AuditActorContext | None]) -> None:
    _actor_ctx.reset(token)


def get_audit_context() -> dict:
    request = _request_ctx.get()
    actor = _actor_ctx.get()
    return {
        "request": request.__dict__ if request else None,
        "actor": actor.__dict__ if actor else None,
    }
