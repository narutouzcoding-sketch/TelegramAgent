"""Revocable device sessions. Only token hashes are retained in the private database."""

import hashlib
import hmac
import secrets
import time


class PanelSessions:
    def __init__(self, store):
        self.store = store
        secret = store.telegram_state("panel_auth_secret")
        if not secret:
            secret = secrets.token_hex(32)
            store.set_telegram_state("panel_auth_secret", secret)
        self.secret = secret.encode()
        with store.db:
            store.db.execute(
                "CREATE TABLE IF NOT EXISTS panel_sessions (token_hash TEXT PRIMARY KEY,csrf TEXT NOT NULL,expires REAL NOT NULL,password_tag TEXT NOT NULL,created REAL NOT NULL)"
            )

    def password_tag(self, password):
        return hmac.new(self.secret, password.encode(), hashlib.sha256).hexdigest()

    def get(self, token, password):
        if not isinstance(token, str) or not 40 <= len(token) <= 100:
            return None
        row = self.store.db.execute(
            "SELECT csrf,expires,password_tag FROM panel_sessions WHERE token_hash=?",
            (hashlib.sha256(token.encode()).hexdigest(),),
        ).fetchone()
        if row is None or row["expires"] <= time.time():
            return None
        if not hmac.compare_digest(row["password_tag"], self.password_tag(password)):
            return None
        return {"csrf": row["csrf"], "expires": row["expires"]}

    def issue(self, password, remember=False):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        lifetime = 30 * 86400 if remember else 8 * 3600
        now = time.time()
        with self.store.db:
            self.store.db.execute("DELETE FROM panel_sessions WHERE expires<=?", (now,))
            self.store.db.execute(
                "DELETE FROM panel_sessions WHERE token_hash IN (SELECT token_hash FROM panel_sessions ORDER BY created DESC LIMIT -1 OFFSET 19)"
            )
            self.store.db.execute(
                "INSERT INTO panel_sessions VALUES(?,?,?,?,?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    csrf,
                    now + lifetime,
                    self.password_tag(password),
                    now,
                ),
            )
        return token, csrf, lifetime

    def revoke(self, token):
        with self.store.db:
            self.store.db.execute(
                "DELETE FROM panel_sessions WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            )

    def revoke_all(self):
        with self.store.db:
            self.store.db.execute("DELETE FROM panel_sessions")


def secure_request(request):
    # HTTPS is terminated by the documented local reverse proxy.
    return request.secure or (
        request.remote in {"127.0.0.1", "::1"}
        and request.headers.get("X-Forwarded-Proto") == "https"
    )
