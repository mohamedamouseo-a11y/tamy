from __future__ import annotations

import hashlib
import hmac

from helpers import dotenv, tamy_users


def _legacy_credentials() -> tuple[str, str]:
    return (
        dotenv.get_dotenv_value(dotenv.KEY_AUTH_LOGIN) or "",
        dotenv.get_dotenv_value(dotenv.KEY_AUTH_PASSWORD) or "",
    )


def _ensure_bootstrap() -> None:
    username, password = _legacy_credentials()
    if username:
        tamy_users.ensure_legacy_superadmin(username, password)


def get_credentials_hash():
    """Legacy compatibility hash for callers/tests that still inspect env auth."""
    user, password = _legacy_credentials()
    if not user:
        return None
    return hashlib.sha256(f"{user}:{password}".encode()).hexdigest()


def is_login_required() -> bool:
    _ensure_bootstrap()
    return tamy_users.has_users()


def authenticate(username: str, password: str) -> dict | None:
    _ensure_bootstrap()
    return tamy_users.authenticate(username, password)


def begin_session(flask_session, user: dict) -> None:
    flask_session["authentication"] = user["session_token"]
    flask_session["username"] = user["username"]
    flask_session["role"] = user["role"]
    flask_session.permanent = True


def clear_session(flask_session) -> None:
    for key in ("authentication", "username", "role"):
        flask_session.pop(key, None)


def current_user(flask_session) -> dict | None:
    if not is_login_required():
        return {"username": "local-admin", "role": tamy_users.ROLE_SUPERADMIN, "active": True}
    username = str(flask_session.get("username") or "")
    token = str(flask_session.get("authentication") or "")
    if not username or not token:
        return None
    user = tamy_users.get_user_private(username)
    if not user or not user.get("active", True):
        return None
    if not hmac.compare_digest(str(user.get("session_token") or ""), token):
        return None
    return user


def is_authenticated_session(flask_session) -> bool:
    return not is_login_required() or current_user(flask_session) is not None


def is_superadmin(flask_session) -> bool:
    user = current_user(flask_session)
    return bool(user and user.get("role") == tamy_users.ROLE_SUPERADMIN)
