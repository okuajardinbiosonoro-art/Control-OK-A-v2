from __future__ import annotations

import sys
from pathlib import Path
import time


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from control_okua.services.remote_session_service import RemoteSessionService  # noqa: E402


def test_remote_session_service_login_logout_and_expiry() -> None:
    service = RemoteSessionService(ttl_s=300)

    session = service.create_session(username="admin.okua")
    cookie_header = service.build_set_cookie_header(session.session_id)

    assert service.has_session_cookie(cookie_header) is True
    assert service.extract_session_id(cookie_header) == session.session_id
    assert service.resolve_session(cookie_header) is not None

    service.destroy_session(session.session_id)
    assert service.resolve_session(cookie_header) is None


def test_remote_session_service_expires_sessions() -> None:
    service = RemoteSessionService(ttl_s=300)
    session = service.create_session(username="admin.okua")
    cookie_header = service.build_set_cookie_header(session.session_id)

    service._sessions[session.session_id] = session.__class__(
        session_id=session.session_id,
        username=session.username,
        created_at_monotonic=session.created_at_monotonic,
        expires_at_monotonic=time.monotonic() - 1.0,
    )

    assert service.resolve_session(cookie_header) is None
