from __future__ import annotations

from dataclasses import dataclass
from http.cookies import SimpleCookie
from threading import Lock
import secrets
import time


DEFAULT_REMOTE_SESSION_TTL_S = 12 * 60 * 60


@dataclass(frozen=True)
class RemoteSessionRecord:
    session_id: str
    username: str
    created_at_monotonic: float
    expires_at_monotonic: float


class RemoteSessionService:
    def __init__(
        self,
        *,
        cookie_name: str = "ckv2_remote_session",
        ttl_s: int = DEFAULT_REMOTE_SESSION_TTL_S,
    ) -> None:
        self._cookie_name = str(cookie_name).strip() or "ckv2_remote_session"
        self._ttl_s = max(300, int(ttl_s))
        self._lock = Lock()
        self._sessions: dict[str, RemoteSessionRecord] = {}

    @property
    def cookie_name(self) -> str:
        return self._cookie_name

    @property
    def ttl_s(self) -> int:
        return self._ttl_s

    def create_session(self, *, username: str) -> RemoteSessionRecord:
        now = time.monotonic()
        session_id = secrets.token_urlsafe(32)
        record = RemoteSessionRecord(
            session_id=session_id,
            username=str(username).strip(),
            created_at_monotonic=now,
            expires_at_monotonic=now + self._ttl_s,
        )
        with self._lock:
            self._sessions[session_id] = record
        return record

    def resolve_session(self, cookie_header: str | None) -> RemoteSessionRecord | None:
        session_id = self.extract_session_id(cookie_header)
        if session_id is None:
            return None
        now = time.monotonic()
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            if record.expires_at_monotonic <= now:
                self._sessions.pop(session_id, None)
                return None
            refreshed = RemoteSessionRecord(
                session_id=record.session_id,
                username=record.username,
                created_at_monotonic=record.created_at_monotonic,
                expires_at_monotonic=now + self._ttl_s,
            )
            self._sessions[session_id] = refreshed
            return refreshed

    def has_session_cookie(self, cookie_header: str | None) -> bool:
        return self.extract_session_id(cookie_header) is not None

    def destroy_session(self, session_id: str | None) -> None:
        text = str(session_id or "").strip()
        if not text:
            return
        with self._lock:
            self._sessions.pop(text, None)

    def destroy_session_from_cookie(self, cookie_header: str | None) -> None:
        self.destroy_session(self.extract_session_id(cookie_header))

    def extract_session_id(self, cookie_header: str | None) -> str | None:
        raw = str(cookie_header or "").strip()
        if not raw:
            return None
        try:
            cookie = SimpleCookie()
            cookie.load(raw)
        except Exception:
            return None
        morsel = cookie.get(self._cookie_name)
        if morsel is None:
            return None
        value = str(morsel.value).strip()
        return value or None

    def build_set_cookie_header(self, session_id: str) -> str:
        return (
            f"{self._cookie_name}={session_id}; Path=/; HttpOnly; SameSite=Lax; Max-Age={self._ttl_s}"
        )

    def build_clear_cookie_header(self) -> str:
        return f"{self._cookie_name}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
