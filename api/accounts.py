"""Sign-up, log-in and the shared demo account (item 24 step 1), behind NODUS_ACCOUNTS=on.

With the flag off every route here answers 404 and the app is today's single-graph demo. A log-in sets an
httpOnly, SameSite=Lax session cookie; a state-changing request authenticated by that cookie must echo the
session's CSRF token in X-CSRF-Token (double submit). Sign-up and log-in are rate-limited per IP.
"""
from __future__ import annotations

import os
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from brain.accounts import AccountError, AccountStore
from brain.db import Graph
from brain.ids import now_ms

COOKIE = "nodus_session"
CSRF_HEADER = "x-csrf-token"
router = APIRouter()
_STORE: dict[str, AccountStore] = {}
_RATE: dict[str, deque] = defaultdict(deque)


def enabled() -> bool:
    return os.environ.get("NODUS_ACCOUNTS") == "on"


def store() -> AccountStore:
    name = os.environ.get("NODUS_ACCOUNTS_GRAPH", "nodus_accounts")
    if name not in _STORE:
        _STORE.clear()
        _STORE[name] = AccountStore(Graph(name=name))
    return _STORE[name]


def demo_credentials() -> tuple[str, str]:
    return os.environ.get("NODUS_DEMO_EMAIL", ""), os.environ.get("NODUS_DEMO_PASSWORD", "")


def current(request: Request) -> dict | None:
    """The logged-in account for this request, or None (flag off, no cookie, or an expired session)."""
    if not enabled():
        return None
    tok = request.cookies.get(COOKIE, "")
    return store().session(tok) if tok else None


def check_csrf(request: Request, account: dict) -> None:
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != account["csrf"]:
        raise HTTPException(403, "missing or wrong CSRF token")


def _limit(request: Request, what: str, n: int = 20, window_ms: int = 3_600_000) -> None:
    ip = request.client.host if request.client else "?"
    if os.environ.get("BRAIN_TRUST_PROXY") == "on" and request.headers.get("x-forwarded-for"):
        ip = request.headers["x-forwarded-for"].split(",")[0].strip()
    q, t = _RATE[f"{what}:{ip}"], now_ms()
    while q and q[0] < t - window_ms:
        q.popleft()
    if len(q) >= n:
        raise HTTPException(429, "too many attempts; try again later")
    q.append(t)


def _need_flag() -> None:
    if not enabled():
        raise HTTPException(404, "accounts are off")


def _set_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=7 * 24 * 3600, path="/",
                    secure=os.environ.get("NODUS_COOKIE_SECURE") == "on")


def _me(account: dict | None) -> dict:
    if not account:
        return {"account": None}
    return {"account": {k: account[k] for k in ("id", "email", "workspace", "demo")}, "csrf": account["csrf"]}


class Credentials(BaseModel):
    email: str
    password: str


@router.post("/auth/signup")
def signup(body: Credentials, request: Request, response: Response) -> dict:
    """Create an account with its own empty workspace, and log in."""
    _need_flag()
    _limit(request, "signup", n=10)
    try:
        store().signup(body.email, body.password)
    except AccountError as e:
        raise HTTPException(400, str(e)) from e
    return login(body, request, response)


@router.post("/auth/login")
def login(body: Credentials, request: Request, response: Response) -> dict:
    """Log in with email and password; sets the session cookie."""
    _need_flag()
    _limit(request, "login")
    got = store().login(body.email, body.password)
    if not got:
        raise HTTPException(401, "wrong email or password")
    _set_cookie(response, got[0])
    return _me(store().session(got[0]))


@router.post("/auth/demo")
def demo_login(request: Request, response: Response) -> dict:
    """Log in to the shared demo account (credentials from NODUS_DEMO_EMAIL / NODUS_DEMO_PASSWORD)."""
    _need_flag()
    email, pw = demo_credentials()
    if not email or not pw:
        raise HTTPException(503, "the demo account isn't configured")
    store().ensure_demo(email, pw)
    return login(Credentials(email=email, password=pw), request, response)


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    """End this session."""
    _need_flag()
    a = current(request)
    if a:
        check_csrf(request, a)
        store().logout(request.cookies.get(COOKIE, ""))
    response.delete_cookie(COOKIE, path="/")
    return {"account": None}


@router.get("/auth/me")
def me(request: Request) -> dict:
    """The logged-in account and its CSRF token, or {account: null}."""
    _need_flag()
    return _me(current(request))


@router.post("/auth/keys")
def create_key(request: Request) -> dict:
    """A new API key for this workspace (for the MCP server). Shown once; older keys are revoked."""
    _need_flag()
    a = current(request)
    if not a:
        raise HTTPException(401, "log in first")
    check_csrf(request, a)
    store().revoke_keys(a["id"])
    return {"key": store().create_key(a["id"]), "workspace": a["workspace"]}
