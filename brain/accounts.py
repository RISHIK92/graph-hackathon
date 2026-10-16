"""Accounts, log-in sessions and API keys (item 24 step 1), in their own graph, never in a workspace graph.

Passwords are argon2 hashes; session and API-key tokens are stored only as SHA-256 hashes, so a copy of this
graph can't log anyone in. Each account owns one workspace, a FalkorDB graph of its own (`ws_<id>`, step 2).
The queries are account plumbing, not brain reads, so they stay inline like schema.py's (no templates).
"""
from __future__ import annotations

import hashlib
import re
import secrets
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from .db import Graph
from .ids import now_ms

SESSION_TTL_MS = 7 * 24 * 3_600_000
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PH = PasswordHasher()


class AccountError(Exception):
    pass


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _account(row: dict) -> dict:
    a = row["a"]
    return {"id": a["id"], "email": a["email"], "workspace": a["workspace"], "demo": bool(a.get("demo")),
            "created_at": a["created_at"]}


class AccountStore:
    def __init__(self, g: Graph):
        self.g = g
        for label, prop in (("Account", "id"), ("Account", "email"), ("LoginSession", "token"), ("ApiKey", "token")):
            try:
                g.write(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})", template="accounts")
            except Exception as e:  # noqa: BLE001
                if "already indexed" not in str(e).lower():
                    raise

    def signup(self, email: str, password: str, demo: bool = False) -> dict:
        email = email.strip().lower()
        if not _EMAIL.match(email):
            raise AccountError("enter a valid email address")
        if len(password) < 8:
            raise AccountError("use a password of at least 8 characters")
        aid = uuid.uuid4().hex[:12]
        # MERGE on the email in one query: two sign-ups with the same address can't both create an account
        rows = self.g.write(
            "MERGE (a:Account {email:$e}) ON CREATE SET a.id = $id, a.pw = $pw, a.workspace = $ws, "
            "a.created_at = $now, a.demo = $demo RETURN a, a.id = $id AS created",
            {"e": email, "id": aid, "pw": _PH.hash(password), "ws": f"ws_{aid}", "now": now_ms(), "demo": demo},
            template="accounts").rows
        if not rows or not rows[0][1]:
            raise AccountError("an account with that email already exists")
        return _account({"a": rows[0][0].properties})

    def _by_email(self, email: str) -> dict | None:
        rows = self.g.ro("MATCH (a:Account {email:$e}) RETURN properties(a) AS a", {"e": email.strip().lower()},
                         template="accounts")
        return rows[0]["a"] if rows else None

    def login(self, email: str, password: str, ttl_ms: int = SESSION_TTL_MS) -> tuple[str, str] | None:
        a = self._by_email(email)
        try:
            if not a or not _PH.verify(a["pw"], password):
                return None
        except VerificationError:
            return None
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        self.g.write("MATCH (a:Account {id:$id}) CREATE (a)<-[:OF_ACCOUNT]-(:LoginSession {token:$t, csrf:$c, "
                     "expires:$x, created_at:$now})",
                     {"id": a["id"], "t": _h(token), "c": csrf, "x": now_ms() + ttl_ms, "now": now_ms()},
                     template="accounts")
        return token, csrf

    def session(self, token: str) -> dict | None:
        if not token:
            return None
        rows = self.g.ro("MATCH (s:LoginSession {token:$t})-[:OF_ACCOUNT]->(a:Account) WHERE s.expires > $now "
                         "RETURN properties(a) AS a, s.csrf AS csrf", {"t": _h(token), "now": now_ms()},
                         template="accounts")
        return {**_account(rows[0]), "csrf": rows[0]["csrf"]} if rows else None

    def logout(self, token: str) -> None:
        self.g.write("MATCH (s:LoginSession {token:$t}) DELETE s", {"t": _h(token)}, template="accounts")

    def create_key(self, account_id: str) -> str:
        key = "nodus_" + secrets.token_urlsafe(24)
        self.g.write("MATCH (a:Account {id:$id}) CREATE (a)<-[:OF_ACCOUNT]-(:ApiKey {token:$t, created_at:$now})",
                     {"id": account_id, "t": _h(key), "now": now_ms()}, template="accounts")
        return key

    def key_account(self, key: str) -> dict | None:
        rows = self.g.ro("MATCH (k:ApiKey {token:$t})-[:OF_ACCOUNT]->(a:Account) RETURN properties(a) AS a",
                         {"t": _h(key)}, template="accounts")
        return _account(rows[0]) if rows else None

    def revoke_keys(self, account_id: str) -> None:
        self.g.write("MATCH (k:ApiKey)-[:OF_ACCOUNT]->(:Account {id:$id}) DELETE k", {"id": account_id},
                     template="accounts")

    def ensure_demo(self, email: str, password: str) -> dict:
        """The one shared demo account (user decision): created on first start, the same account after."""
        a = self._by_email(email)
        if a:
            return _account({"a": a})
        try:
            return self.signup(email, password, demo=True)
        except AccountError:
            return _account({"a": self._by_email(email)})
