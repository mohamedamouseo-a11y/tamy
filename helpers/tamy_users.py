from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading

ROLE_SUPERADMIN = "superadmin"
ROLE_USER = "user"
VALID_ROLES = {ROLE_SUPERADMIN, ROLE_USER}
PBKDF2_ITERATIONS = 310_000
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
_LOCK = threading.RLock()
_USERS_FILE = Path(__file__).resolve().parents[1] / "usr" / "tamy_users.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_store() -> dict:
    return {"version": 1, "users": []}


def _load() -> dict:
    if not _USERS_FILE.is_file():
        return _empty_store()
    try:
        data = json.loads(_USERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Tamy user database is unreadable") from exc
    if not isinstance(data, dict) or not isinstance(data.get("users"), list):
        raise RuntimeError("Tamy user database has an invalid format")
    return data


def _save(data: dict) -> None:
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = _USERS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    os.replace(temp, _USERS_FILE)


def _validate_username(username: str) -> str:
    username = str(username or "").strip()
    if not _USERNAME_RE.fullmatch(username):
        raise ValueError("Username must be 3-64 characters using letters, numbers, dot, dash, or underscore")
    return username


def _validate_password(password: str) -> str:
    password = str(password or "")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    return password


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return base64.b64encode(salt).decode("ascii"), base64.b64encode(digest).decode("ascii")


def _verify_password(user: dict, password: str) -> bool:
    try:
        salt = base64.b64decode(user["password_salt"])
        expected = base64.b64decode(user["password_hash"])
    except (KeyError, ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(actual, expected)


def _find(data: dict, username: str) -> dict | None:
    key = str(username or "").strip().casefold()
    return next((user for user in data["users"] if str(user.get("username", "")).casefold() == key), None)


def _public(user: dict) -> dict:
    return {
        "username": user["username"],
        "role": user["role"],
        "active": bool(user.get("active", True)),
        "created_at": user.get("created_at", ""),
        "updated_at": user.get("updated_at", ""),
    }


def _active_superadmin_count(data: dict, excluding: str | None = None) -> int:
    excluded = excluding.casefold() if excluding else None
    return sum(
        1 for user in data["users"]
        if user.get("active", True)
        and user.get("role") == ROLE_SUPERADMIN
        and (excluded is None or user.get("username", "").casefold() != excluded)
    )


def has_users() -> bool:
    with _LOCK:
        return bool(_load()["users"])


def ensure_legacy_superadmin(username: str, password: str) -> None:
    """Bootstrap existing AUTH_LOGIN/AUTH_PASSWORD exactly as configured."""
    username = str(username or "").strip()
    if not username:
        return
    password = str(password or "")
    with _LOCK:
        data = _load()
        if data["users"]:
            return
        salt, password_hash = _hash_password(password)
        now = _now()
        data["users"].append({
            "username": username,
            "role": ROLE_SUPERADMIN,
            "active": True,
            "password_salt": salt,
            "password_hash": password_hash,
            "session_token": secrets.token_urlsafe(32),
            "created_at": now,
            "updated_at": now,
        })
        _save(data)


def authenticate(username: str, password: str) -> dict | None:
    with _LOCK:
        user = _find(_load(), username)
        if not user or not user.get("active", True) or not _verify_password(user, str(password or "")):
            return None
        return dict(user)


def get_user_private(username: str) -> dict | None:
    with _LOCK:
        user = _find(_load(), username)
        return dict(user) if user else None


def list_users() -> list[dict]:
    with _LOCK:
        return [_public(user) for user in sorted(_load()["users"], key=lambda item: item["username"].casefold())]


def create_user(username: str, password: str, role: str = ROLE_USER, active: bool = True) -> dict:
    username = _validate_username(username)
    password = _validate_password(password)
    role = str(role or ROLE_USER).strip().lower()
    if role not in VALID_ROLES:
        raise ValueError("Invalid role")
    with _LOCK:
        data = _load()
        if _find(data, username):
            raise ValueError("Username already exists")
        if not data["users"]:
            role = ROLE_SUPERADMIN
            active = True
        salt, password_hash = _hash_password(password)
        now = _now()
        user = {
            "username": username,
            "role": role,
            "active": bool(active),
            "password_salt": salt,
            "password_hash": password_hash,
            "session_token": secrets.token_urlsafe(32),
            "created_at": now,
            "updated_at": now,
        }
        data["users"].append(user)
        _save(data)
        return _public(user)


def update_user(username: str, *, role: str | None = None, active: bool | None = None, password: str | None = None) -> dict:
    with _LOCK:
        data = _load()
        user = _find(data, username)
        if not user:
            raise ValueError("User not found")
        next_role = user["role"] if role is None else str(role).strip().lower()
        next_active = bool(user.get("active", True)) if active is None else bool(active)
        if next_role not in VALID_ROLES:
            raise ValueError("Invalid role")
        removing_last_admin = (
            user.get("role") == ROLE_SUPERADMIN
            and user.get("active", True)
            and (next_role != ROLE_SUPERADMIN or not next_active)
            and _active_superadmin_count(data, excluding=user["username"]) == 0
        )
        if removing_last_admin:
            raise ValueError("At least one active superadmin is required")
        changed = next_role != user["role"] or next_active != bool(user.get("active", True))
        user["role"] = next_role
        user["active"] = next_active
        if password is not None and str(password) != "":
            password = _validate_password(password)
            user["password_salt"], user["password_hash"] = _hash_password(password)
            changed = True
        if changed:
            user["session_token"] = secrets.token_urlsafe(32)
            user["updated_at"] = _now()
            _save(data)
        return _public(user)


def delete_user(username: str) -> None:
    with _LOCK:
        data = _load()
        user = _find(data, username)
        if not user:
            raise ValueError("User not found")
        if (
            user.get("role") == ROLE_SUPERADMIN
            and user.get("active", True)
            and _active_superadmin_count(data, excluding=user["username"]) == 0
        ):
            raise ValueError("The last active superadmin cannot be deleted")
        data["users"].remove(user)
        _save(data)
