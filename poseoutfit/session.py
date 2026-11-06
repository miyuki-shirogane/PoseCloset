from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .config import Config
from .errors import INVALID_STATE, SESSION_NOT_FOUND, SkillError

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id    TEXT,
    version    INTEGER NOT NULL,
    updated_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    data       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
"""


def _now() -> float:
    return time.time()


class SessionStore:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.path = Path(config.state_dir) / "sessions.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def create(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        now = _now()
        data: Dict[str, Any] = {
            "session_id": str(uuid.uuid4()),
            "user_id": user_id,
            "state": "pose_category",
            "version": 1,
            "pose_id": None,
            "outfit_id": None,
            "pose_batch": None,
            "outfit_batch": None,
            "seen": {"pose": {}, "outfit": {}},
            "subject": None,
            "spec": None,
            "render": None,
            "created_at": now,
            "updated_at": now,
            "expires_at": now + self.config.session_ttl_hours * 3600,
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions(session_id,user_id,version,updated_at,expires_at,data) VALUES(?,?,?,?,?,?)",
                (data["session_id"], user_id, 1, now, data["expires_at"], json.dumps(data, ensure_ascii=False)),
            )
        return data

    def read(self, session_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise SkillError(SESSION_NOT_FOUND, "会话不存在或已过期")
        if row["expires_at"] < _now():
            self.drop(session_id)
            raise SkillError(SESSION_NOT_FOUND, "会话已过期")
        return json.loads(row["data"])

    def mutate(self, session_id: str, fn: Callable[[Dict[str, Any]], Any]) -> Dict[str, Any]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if row is None:
                raise SkillError(SESSION_NOT_FOUND, "会话不存在或已过期")
            if row["expires_at"] < _now():
                conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
                conn.execute("COMMIT")
                raise SkillError(SESSION_NOT_FOUND, "会话已过期")
            data = json.loads(row["data"])
            fn(data)
            data["version"] = int(row["version"]) + 1
            data["updated_at"] = _now()
            data["expires_at"] = _now() + self.config.session_ttl_hours * 3600
            conn.execute(
                "UPDATE sessions SET version=?,updated_at=?,expires_at=?,data=? WHERE session_id=?",
                (
                    data["version"],
                    data["updated_at"],
                    data["expires_at"],
                    json.dumps(data, ensure_ascii=False),
                    session_id,
                ),
            )
            conn.execute("COMMIT")
            return data
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    def drop(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))

    def purge_expired(self) -> int:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_now(),))
            return cur.rowcount or 0


def require_state(data: Dict[str, Any], *states: str) -> None:
    if data["state"] not in states:
        raise SkillError(
            INVALID_STATE,
            "当前状态 %s 不允许该操作" % data["state"],
            extra={"state": data["state"], "allowed_actions": allowed_actions(data["state"])},
        )


def allowed_actions(state: str):
    from .state_machine import ALLOWED_ACTIONS

    return list(ALLOWED_ACTIONS.get(state, []))
