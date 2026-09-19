from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .security import hash_password, normalize_email, normalize_phone, token_hash, utc_now


BUSINESS_FIELDS = {
    "name",
    "industry",
    "area",
    "greeting",
    "services",
    "business_hours",
    "notification_email",
    "fallback_phone",
    "assistant_name",
    "voice",
    "extra_instructions",
    "conversation_pace",
    "timezone",
    "onboarding_completed",
}


class Database:
    def __init__(self, path: Path, settings: Settings):
        self.path = path
        self.settings = settings

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    terms_accepted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS businesses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    industry TEXT NOT NULL DEFAULT '',
                    area TEXT NOT NULL DEFAULT '',
                    phone_display TEXT NOT NULL DEFAULT '',
                    phone_e164 TEXT UNIQUE,
                    phone_status TEXT NOT NULL DEFAULT 'pending',
                    greeting TEXT NOT NULL DEFAULT '',
                    services TEXT NOT NULL DEFAULT '',
                    business_hours TEXT NOT NULL DEFAULT '',
                    notification_email TEXT NOT NULL DEFAULT '',
                    fallback_phone TEXT NOT NULL DEFAULT '',
                    assistant_name TEXT NOT NULL DEFAULT 'Nottle',
                    voice TEXT NOT NULL DEFAULT 'marin',
                    extra_instructions TEXT NOT NULL DEFAULT '',
                    conversation_pace TEXT NOT NULL DEFAULT 'patient',
                    timezone TEXT NOT NULL DEFAULT 'Australia/Perth',
                    plan TEXT NOT NULL DEFAULT 'starter',
                    subscription_status TEXT NOT NULL DEFAULT 'trial',
                    trial_ends_at TEXT,
                    onboarding_completed INTEGER NOT NULL DEFAULT 0,
                    is_system_default INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    user_agent TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS password_resets (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                );

                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_id INTEGER REFERENCES businesses(id) ON DELETE CASCADE,
                    stream_sid TEXT,
                    call_sid TEXT,
                    caller TEXT,
                    called_number TEXT NOT NULL DEFAULT '',
                    created_at TEXT,
                    completed_at TEXT,
                    duration_seconds INTEGER NOT NULL DEFAULT 0,
                    status TEXT DEFAULT 'in_progress',
                    transcript TEXT DEFAULT '',
                    summary TEXT DEFAULT '',
                    is_lead INTEGER DEFAULT 1,
                    booking_requested INTEGER DEFAULT 0,
                    error_message TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                """
            )
            self._upgrade_legacy_calls(conn)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_calls_business_created "
                "ON calls(business_id, created_at DESC)"
            )
            default_business_id = self._ensure_default_business(conn)
            self._ensure_admin(conn, default_business_id)
            conn.execute(
                "DELETE FROM sessions WHERE expires_at < ?",
                (utc_now(),),
            )

    @staticmethod
    def _upgrade_legacy_calls(conn: sqlite3.Connection) -> None:
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(calls)").fetchall()
        }
        additions = {
            "business_id": "INTEGER REFERENCES businesses(id) ON DELETE CASCADE",
            "called_number": "TEXT NOT NULL DEFAULT ''",
            "completed_at": "TEXT",
            "duration_seconds": "INTEGER NOT NULL DEFAULT 0",
            "error_message": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in additions.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE calls ADD COLUMN {name} {definition}")

    def _ensure_default_business(self, conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT id FROM businesses WHERE is_system_default=1 LIMIT 1"
        ).fetchone()
        phone_e164 = normalize_phone(self.settings.default_business_phone)
        now = utc_now()
        if row:
            conn.execute(
                """
                UPDATE businesses
                SET name=?, area=?, phone_display=?, phone_e164=?, phone_status='active',
                    updated_at=?
                WHERE id=?
                """,
                (
                    self.settings.default_business_name,
                    self.settings.default_business_area,
                    self.settings.default_business_phone,
                    phone_e164 or None,
                    now,
                    row["id"],
                ),
            )
            business_id = int(row["id"])
        else:
            trial_end = (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat()
            cur = conn.execute(
                """
                INSERT INTO businesses(
                    name, industry, area, phone_display, phone_e164, phone_status,
                    notification_email, services, business_hours, subscription_status,
                    trial_ends_at, onboarding_completed, is_system_default, created_at, updated_at
                ) VALUES(?,?,?,?,?,'active',?,?,?,'active',?,1,1,?,?)
                """,
                (
                    self.settings.default_business_name,
                    "Property services",
                    self.settings.default_business_area,
                    self.settings.default_business_phone,
                    phone_e164 or None,
                    self.settings.support_email,
                    "Property maintenance, cleaning, gardening and project enquiries",
                    "By appointment",
                    trial_end,
                    now,
                    now,
                ),
            )
            business_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE calls SET business_id=? WHERE business_id IS NULL", (business_id,)
        )
        return business_id

    def _ensure_admin(self, conn: sqlite3.Connection, business_id: int) -> None:
        if not self.settings.admin_email or len(self.settings.admin_password) < 10:
            return
        now = utc_now()
        user = conn.execute(
            "SELECT id FROM users WHERE email=?", (self.settings.admin_email,)
        ).fetchone()
        if user:
            user_id = int(user["id"])
            conn.execute("UPDATE users SET is_admin=1 WHERE id=?", (user_id,))
        else:
            cur = conn.execute(
                """
                INSERT INTO users(email,password_hash,full_name,is_admin,terms_accepted_at,created_at,updated_at)
                VALUES(?,?,?,1,?,?,?)
                """,
                (
                    self.settings.admin_email,
                    hash_password(self.settings.admin_password),
                    "Daniel Nottle",
                    now,
                    now,
                    now,
                ),
            )
            user_id = int(cur.lastrowid)
        conn.execute(
            """
            UPDATE businesses SET owner_user_id=?, notification_email=?, updated_at=?
            WHERE id=? AND (owner_user_id IS NULL OR owner_user_id=?)
            """,
            (user_id, self.settings.admin_email, now, business_id, user_id),
        )

    @staticmethod
    def _dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def create_user_and_business(
        self, *, email: str, password_hash: str, full_name: str, business_name: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        email = normalize_email(email)
        now = utc_now()
        trial_end = (
            datetime.now(timezone.utc) + timedelta(days=self.settings.trial_days)
        ).isoformat()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO users(email,password_hash,full_name,is_admin,terms_accepted_at,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    email,
                    password_hash,
                    full_name.strip(),
                    1 if email == self.settings.admin_email else 0,
                    now,
                    now,
                    now,
                ),
            )
            user_id = int(cur.lastrowid)
            cur = conn.execute(
                """
                INSERT INTO businesses(
                    owner_user_id,name,notification_email,trial_ends_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (user_id, business_name.strip(), email, trial_end, now, now),
            )
            business_id = int(cur.lastrowid)
            user = self._dict(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
            business = self._dict(
                conn.execute("SELECT * FROM businesses WHERE id=?", (business_id,)).fetchone()
            )
        return user or {}, business or {}

    def user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            return self._dict(
                conn.execute(
                    "SELECT * FROM users WHERE email=?", (normalize_email(email),)
                ).fetchone()
            )

    def create_session(self, raw_token: str, user_id: int, user_agent: str) -> str:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        expires = (now_dt + timedelta(days=self.settings.session_days)).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(token_hash,user_id,created_at,expires_at,last_seen_at,user_agent)
                VALUES(?,?,?,?,?,?)
                """,
                (token_hash(raw_token), user_id, now, expires, now, user_agent[:500]),
            )
        return expires

    def session_user(self, raw_token: str) -> dict[str, Any] | None:
        now = utc_now()
        digest = token_hash(raw_token)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT u.* FROM sessions s
                JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.expires_at>?
                """,
                (digest, now),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE sessions SET last_seen_at=? WHERE token_hash=?", (now, digest)
                )
            return self._dict(row)

    def revoke_session(self, raw_token: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(raw_token),))

    def revoke_all_sessions(self, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))

    def business_for_user(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            return self._dict(
                conn.execute(
                    "SELECT * FROM businesses WHERE owner_user_id=?", (user_id,)
                ).fetchone()
            )

    def business_by_id(self, business_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            return self._dict(
                conn.execute(
                    "SELECT * FROM businesses WHERE id=?", (business_id,)
                ).fetchone()
            )

    def business_by_phone(self, phone: str) -> dict[str, Any] | None:
        normalized = normalize_phone(phone)
        if not normalized:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM businesses WHERE phone_e164=? AND phone_status='active'",
                (normalized,),
            ).fetchone()
            return self._dict(row)

    def update_business(self, business_id: int, values: dict[str, Any]) -> dict[str, Any]:
        clean = {k: v for k, v in values.items() if k in BUSINESS_FIELDS}
        if "onboarding_completed" in clean:
            clean["onboarding_completed"] = 1 if clean["onboarding_completed"] else 0
        if not clean:
            business = self.business_by_id(business_id)
            return business or {}
        clean["updated_at"] = utc_now()
        assignments = ",".join(f"{key}=?" for key in clean)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE businesses SET {assignments} WHERE id=?",
                (*clean.values(), business_id),
            )
            row = conn.execute(
                "SELECT * FROM businesses WHERE id=?", (business_id,)
            ).fetchone()
            return self._dict(row) or {}

    def dashboard(self, business_id: int) -> dict[str, int]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS calls,
                       COALESCE(SUM(is_lead),0) AS leads,
                       COALESCE(SUM(booking_requested),0) AS bookings,
                       COALESCE(SUM(duration_seconds),0) AS seconds
                FROM calls WHERE business_id=?
                """,
                (business_id,),
            ).fetchone()
        return {key: int(row[key] or 0) for key in ("calls", "leads", "bookings", "seconds")}

    def calls_for_business(self, business_id: int, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM calls WHERE business_id=?
                ORDER BY id DESC LIMIT ?
                """,
                (business_id, min(max(limit, 1), 200)),
            ).fetchall()
        return [dict(row) for row in rows]

    def call_for_business(self, business_id: int, call_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            return self._dict(
                conn.execute(
                    "SELECT * FROM calls WHERE id=? AND business_id=?",
                    (call_id, business_id),
                ).fetchone()
            )

    def delete_call(self, business_id: int, call_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM calls WHERE id=? AND business_id=?",
                (call_id, business_id),
            )
            return cur.rowcount > 0

    def create_call(
        self,
        *,
        business_id: int,
        stream_sid: str,
        call_sid: str,
        caller: str,
        called_number: str,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO calls(
                    business_id,stream_sid,call_sid,caller,called_number,created_at,status
                ) VALUES(?,?,?,?,?,?,'in_progress')
                """,
                (business_id, stream_sid, call_sid, caller, called_number, utc_now()),
            )
            return int(cur.lastrowid)

    def finish_call(
        self,
        call_id: int,
        *,
        status: str,
        transcript: str,
        summary: str,
        booking_requested: bool,
        duration_seconds: int,
        error_message: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE calls SET status=?,transcript=?,summary=?,booking_requested=?,
                    duration_seconds=?,completed_at=?,error_message=? WHERE id=?
                """,
                (
                    status,
                    transcript[-30000:],
                    summary[:1000],
                    1 if booking_requested else 0,
                    max(0, duration_seconds),
                    utc_now(),
                    error_message[:1000],
                    call_id,
                ),
            )

    def create_password_reset(self, user_id: int, raw_token: str) -> None:
        now_dt = datetime.now(timezone.utc)
        with self.connect() as conn:
            conn.execute("DELETE FROM password_resets WHERE user_id=?", (user_id,))
            conn.execute(
                """
                INSERT INTO password_resets(token_hash,user_id,created_at,expires_at)
                VALUES(?,?,?,?)
                """,
                (
                    token_hash(raw_token),
                    user_id,
                    now_dt.isoformat(),
                    (now_dt + timedelta(hours=1)).isoformat(),
                ),
            )

    def consume_password_reset(self, raw_token: str, password_hash: str) -> bool:
        now = utc_now()
        digest = token_hash(raw_token)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT user_id FROM password_resets
                WHERE token_hash=? AND used_at IS NULL AND expires_at>?
                """,
                (digest, now),
            ).fetchone()
            if not row:
                return False
            conn.execute(
                "UPDATE users SET password_hash=?,updated_at=? WHERE id=?",
                (password_hash, now, row["user_id"]),
            )
            conn.execute(
                "UPDATE password_resets SET used_at=? WHERE token_hash=?", (now, digest)
            )
            conn.execute("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
            return True

    def delete_user(self, user_id: int) -> None:
        with self.connect() as conn:
            system = conn.execute(
                """
                SELECT id FROM businesses
                WHERE owner_user_id=? AND is_system_default=1
                """,
                (user_id,),
            ).fetchone()
            if system:
                conn.execute(
                    "DELETE FROM calls WHERE business_id=?", (system["id"],)
                )
                conn.execute(
                    "UPDATE businesses SET owner_user_id=NULL,updated_at=? WHERE id=?",
                    (utc_now(), system["id"]),
                )
            conn.execute("DELETE FROM users WHERE id=?", (user_id,))

    def admin_businesses(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT b.*,u.email AS owner_email,u.full_name AS owner_name,
                       COUNT(c.id) AS call_count
                FROM businesses b
                LEFT JOIN users u ON u.id=b.owner_user_id
                LEFT JOIN calls c ON c.business_id=b.id
                GROUP BY b.id ORDER BY b.id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def admin_update_business(
        self,
        business_id: int,
        *,
        phone_display: str | None = None,
        phone_status: str | None = None,
        subscription_status: str | None = None,
        plan: str | None = None,
    ) -> dict[str, Any] | None:
        values: dict[str, Any] = {"updated_at": utc_now()}
        if phone_display is not None:
            values["phone_display"] = phone_display.strip()
            values["phone_e164"] = normalize_phone(phone_display) or None
        if phone_status in {"pending", "active", "paused"}:
            values["phone_status"] = phone_status
        if subscription_status in {"trial", "active", "past_due", "paused", "cancelled"}:
            values["subscription_status"] = subscription_status
        if plan in {"starter", "growth", "pro"}:
            values["plan"] = plan
        assignments = ",".join(f"{key}=?" for key in values)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE businesses SET {assignments} WHERE id=?",
                (*values.values(), business_id),
            )
            return self._dict(
                conn.execute(
                    "SELECT * FROM businesses WHERE id=?", (business_id,)
                ).fetchone()
            )
