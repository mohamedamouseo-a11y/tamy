from pathlib import Path
import py_compile

root = Path(__file__).resolve().parents[2]


def write(path, content):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path, old, new):
    target = root / path
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path, marker, content):
    target = root / path
    text = target.read_text(encoding="utf-8") if target.exists() else ""
    if marker in text:
        return
    if text and not text.endswith("\n"):
        text += "\n"
    target.write_text(text + "\n" + content.strip() + "\n", encoding="utf-8")


write("helpers/tamy_users.py", '''from __future__ import annotations

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
    username = str(username or "").strip()
    if not username:
        return
    with _LOCK:
        data = _load()
        if data["users"]:
            return
        password = _validate_password(password)
        username = _validate_username(username)
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
''')

write("helpers/tamy_users.py.dox.md", '''# tamy_users.py DOX

## Purpose
- Own Tamy local user persistence, password verification, roles, and session-token rotation.
- Support exactly `superadmin` and `user` roles.

## Runtime Contracts
- User records live in ignored runtime state at `usr/tamy_users.json`; credentials are never committed.
- Passwords use salted PBKDF2-HMAC-SHA256 hashes; plaintext passwords are never stored.
- Password, role, or active-state changes rotate the user's session token.
- The last active superadmin cannot be disabled, demoted, or deleted.
- Existing `AUTH_LOGIN` / `AUTH_PASSWORD` credentials are bootstrapped once as the first superadmin for backward compatibility.

## Verification
- Run `python -m unittest tests.test_tamy_users` and auth/security tests after changes.
''')

write("helpers/login.py", '''from __future__ import annotations

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
''')

append_once("helpers/login.py.dox.md", "## Tamy RBAC", '''## Tamy RBAC
- Login authenticates against the Tamy runtime user store while preserving the legacy environment credential hash API.
- `AUTH_LOGIN` / `AUTH_PASSWORD` bootstrap the first `superadmin` once.
- Flask sessions carry username, role, and a revocable per-user session token.
- `is_authenticated_session()` and `is_superadmin()` are the authorization entry points for HTTP/API code.
''')

replace_once("helpers/api.py", '''    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def get_methods(cls) -> list[str]:''', '''    @classmethod
    def requires_auth(cls) -> bool:
        return True

    @classmethod
    def requires_superadmin(cls) -> bool:
        return False

    @classmethod
    def get_methods(cls) -> list[str]:''')

replace_once("helpers/api.py", '''def requires_auth(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        from helpers import login

        user_pass_hash = login.get_credentials_hash()
        if not user_pass_hash:
            return await f(*args, **kwargs)
        if session.get("authentication") != user_pass_hash:
            return redirect(url_for("login_handler", next=get_current_request_next_url()))
        return await f(*args, **kwargs)

    return decorated


def csrf_protect(f):''', '''def requires_auth(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        from helpers import login

        if not login.is_login_required():
            return await f(*args, **kwargs)
        if not login.is_authenticated_session(session):
            return redirect(url_for("login_handler", next=get_current_request_next_url()))
        return await f(*args, **kwargs)

    return decorated


def requires_superadmin(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        from helpers import login

        if not login.is_superadmin(session):
            return Response("Superadmin access required", 403, mimetype="text/plain")
        return await f(*args, **kwargs)

    return decorated


def csrf_protect(f):''')

replace_once("helpers/api.py", '''        if handler_cls.requires_api_key():
            handler_fn = requires_api_key(handler_fn)
        if handler_cls.requires_auth():
            handler_fn = requires_auth(handler_fn)''', '''        if handler_cls.requires_api_key():
            handler_fn = requires_api_key(handler_fn)
        if handler_cls.requires_superadmin():
            handler_fn = requires_superadmin(handler_fn)
        if handler_cls.requires_auth():
            handler_fn = requires_auth(handler_fn)''')

append_once("helpers/api.py.dox.md", "## Tamy role authorization", '''## Tamy role authorization
- API handlers may override `requires_superadmin()` to restrict a route to the Tamy superadmin role.
- Authentication validates the current Tamy user session rather than comparing a single global credential hash.
- Superadmin authorization is enforced server-side and returns HTTP 403 for ordinary users.
''')

replace_once("helpers/ui_server.py", '''        if request.method == "POST":
            user = dotenv.get_dotenv_value("AUTH_LOGIN")
            password = dotenv.get_dotenv_value("AUTH_PASSWORD")

            if request.form["username"] == user and request.form["password"] == password:
                session["authentication"] = login.get_credentials_hash()
                return redirect(next_url or fallback_url)
            else:
                await asyncio.sleep(1)
                error = "Invalid Credentials. Please try again."''', '''        if request.method == "POST":
            user = login.authenticate(
                request.form.get("username", ""),
                request.form.get("password", ""),
            )

            if user:
                login.begin_session(session, user)
                return redirect(next_url or fallback_url)
            await asyncio.sleep(1)
            error = "Invalid Credentials. Please try again."''')

replace_once("helpers/ui_server.py", '''    async def logout_handler(self):
        session.pop("authentication", None)
        return redirect(url_for("login_handler"))''', '''    async def logout_handler(self):
        login.clear_session(session)
        return redirect(url_for("login_handler"))''')

replace_once("helpers/ui_server.py", '''        index = files.read_file("webui/index.html")
        return files.replace_placeholders_text(''', '''        current_identity = login.current_user(session) or {}
        current_user_json = json.dumps(str(current_identity.get("username") or ""))
        current_role_json = json.dumps(str(current_identity.get("role") or ""))

        index = files.read_file("webui/index.html")
        return files.replace_placeholders_text(''')

replace_once("helpers/ui_server.py", '''            logged_in=("true" if login.get_credentials_hash() else "false"),
            user_timezone_setting=user_timezone_setting,''', '''            logged_in=("true" if login.is_authenticated_session(session) else "false"),
            current_user_json=current_user_json,
            current_role_json=current_role_json,
            is_superadmin=("true" if login.is_superadmin(session) else "false"),
            user_timezone_setting=user_timezone_setting,''')

append_once("helpers/ui_server.py.dox.md", "## Tamy multi-user login", '''## Tamy multi-user login
- `/login` authenticates Tamy runtime users and stores a revocable username/role/session token tuple in Flask session state.
- `/logout` clears all Tamy identity session fields.
- The WebUI receives the current username, role, and `isSuperAdmin` flag through `runtimeInfo`; backend checks remain authoritative.
''')

replace_once("api/settings_get.py", '''class GetSettings(ApiHandler):
    async def process''', '''class GetSettings(ApiHandler):
    @classmethod
    def requires_superadmin(cls) -> bool:
        return True

    async def process''')
replace_once("api/settings_set.py", '''class SetSettings(ApiHandler):
    async def process''', '''class SetSettings(ApiHandler):
    @classmethod
    def requires_superadmin(cls) -> bool:
        return True

    async def process''')
append_once("api/settings_get.py.dox.md", "## Tamy authorization", "## Tamy authorization\n- Global settings reads are superadmin-only because the payload contains provider/system configuration.")
append_once("api/settings_set.py.dox.md", "## Tamy authorization", "## Tamy authorization\n- Global settings writes are superadmin-only.")

write("api/tamy_users.py", '''import json

from flask import Response

from helpers.api import ApiHandler, Request
from helpers import tamy_users


class TamyUsers(ApiHandler):
    @classmethod
    def requires_superadmin(cls) -> bool:
        return True

    async def process(self, input: dict, request: Request) -> dict | Response:
        action = str(input.get("action") or "list").strip().lower()
        try:
            if action == "list":
                return {"ok": True, "users": tamy_users.list_users()}
            if action == "create":
                user = tamy_users.create_user(
                    input.get("username", ""), input.get("password", ""),
                    input.get("role", tamy_users.ROLE_USER), input.get("active", True),
                )
                return {"ok": True, "user": user, "users": tamy_users.list_users()}
            if action == "update":
                kwargs = {}
                if "role" in input:
                    kwargs["role"] = input.get("role")
                if "active" in input:
                    kwargs["active"] = input.get("active")
                if input.get("password"):
                    kwargs["password"] = input.get("password")
                user = tamy_users.update_user(input.get("username", ""), **kwargs)
                return {"ok": True, "user": user, "users": tamy_users.list_users()}
            if action == "delete":
                tamy_users.delete_user(input.get("username", ""))
                return {"ok": True, "users": tamy_users.list_users()}
            return _error("Unknown user action", 400)
        except ValueError as exc:
            return _error(str(exc), 400)


def _error(message: str, status: int) -> Response:
    return Response(response=json.dumps({"ok": False, "error": message}), status=status, mimetype="application/json")
''')
write("api/tamy_users.py.dox.md", '''# tamy_users.py DOX

## Purpose
- Superadmin-only API for listing, creating, updating, disabling, promoting/demoting, password-resetting, and deleting Tamy users.

## Security
- The endpoint never returns password hashes, salts, or session tokens.
- `requires_superadmin()` enforces server-side authorization before the handler runs.
- User-store invariants prevent removal of the last active superadmin.
''')

replace_once("webui/index.html", '''            loggedIn: "{{logged_in}}" === "true",
            timezone:''', '''            loggedIn: "{{logged_in}}" === "true",
            currentUser: {{current_user_json}},
            currentRole: {{current_role_json}},
            isSuperAdmin: {{is_superadmin}},
            timezone:''')

users_tab = '''  {
    id: "users",
    label: "Users & Access",
    icon: "manage_accounts",
    sections: [
      { id: "section-users", label: "Users", icon: "group" },
    ],
  },
'''
replace_once("webui/components/settings/settings-store.js", '''  {
    id: "backup",
    label: "Check for updates",''', users_tab + '''  {
    id: "backup",
    label: "Check for updates",''')
replace_once("webui/components/settings/settings.html", '''          <div class="settings-tab-panel" data-settings-tab="skills" x-show="$store.settings.activeTab === 'skills'">
            <x-component path="settings/skills/skills-settings.html"></x-component>
          </div>''', '''          <div class="settings-tab-panel" data-settings-tab="skills" x-show="$store.settings.activeTab === 'skills'">
            <x-component path="settings/skills/skills-settings.html"></x-component>
          </div>
          <div class="settings-tab-panel" data-settings-tab="users" x-show="$store.settings.activeTab === 'users'">
            <x-component path="settings/users/users.html"></x-component>
          </div>''')

write("webui/components/settings/users/users-store.js", '''import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";
import { store as notificationStore } from "/components/notifications/notification-store.js";

function toast(text, type = "info") {
  notificationStore.addFrontendToastOnly(type, text, "", 4);
}

const model = {
  users: [],
  loading: false,
  draft: { username: "", password: "", role: "user" },
  async load() {
    this.loading = true;
    try {
      const result = await callJsonApi("tamy_users", { action: "list" });
      this.setUsers(result?.users || []);
    } catch (error) { toast(error?.message || "Unable to load users", "error"); }
    finally { this.loading = false; }
  },
  cleanup() { this.users = []; this.draft = { username: "", password: "", role: "user" }; },
  setUsers(users) { this.users = (users || []).map((user) => ({ ...user, newPassword: "" })); },
  async createUser() {
    if (!this.draft.username || !this.draft.password) return toast("Username and password are required", "warning");
    await this.run({ action: "create", ...this.draft }, "User created");
    this.draft = { username: "", password: "", role: "user" };
  },
  async setRole(user, role) { await this.run({ action: "update", username: user.username, role }, "Role updated"); },
  async setActive(user, active) { await this.run({ action: "update", username: user.username, active }, active ? "User enabled" : "User disabled"); },
  async resetPassword(user) {
    if (!user.newPassword) return toast("Enter a new password first", "warning");
    await this.run({ action: "update", username: user.username, password: user.newPassword }, "Password updated");
  },
  async deleteUser(user) {
    if (!window.confirm(`Delete ${user.username}?`)) return;
    await this.run({ action: "delete", username: user.username }, "User deleted");
  },
  async run(payload, successMessage) {
    this.loading = true;
    try {
      const result = await callJsonApi("tamy_users", payload);
      if (result?.ok === false) throw new Error(result.error || "Request failed");
      this.setUsers(result?.users || []);
      toast(successMessage, "success");
    } catch (error) { toast(error?.message || "User action failed", "error"); }
    finally { this.loading = false; }
  },
};

export const store = createStore("tamyUsers", model);
''')

write("webui/components/settings/users/users.html", '''<html>
<head>
  <script type="module">
    import { store as tamyUsersStore } from "/components/settings/users/users-store.js";
  </script>
</head>
<body>
  <section id="section-users" class="settings-section tamy-users" x-data x-create="$store.tamyUsers.load()" x-destroy="$store.tamyUsers.cleanup()">
    <div><h2>Users & Access</h2><p class="tamy-users-muted">Super Admins manage system settings. Standard users can use Tamy without access to providers, API keys, plugins, or system configuration.</p></div>
    <div class="tamy-user-create">
      <input type="text" placeholder="Username" autocomplete="off" x-model="$store.tamyUsers.draft.username">
      <input type="password" placeholder="Temporary password" autocomplete="new-password" x-model="$store.tamyUsers.draft.password">
      <select x-model="$store.tamyUsers.draft.role"><option value="user">User</option><option value="superadmin">Super Admin</option></select>
      <button type="button" class="btn btn-ok" @click="$store.tamyUsers.createUser()" :disabled="$store.tamyUsers.loading">Add user</button>
    </div>
    <div class="tamy-user-list">
      <template x-for="user in $store.tamyUsers.users" :key="user.username">
        <article class="tamy-user-row">
          <div class="tamy-user-identity"><strong x-text="user.username"></strong><span class="tamy-role-badge" :class="`role-${user.role}`" x-text="user.role === 'superadmin' ? 'Super Admin' : 'User'"></span><span class="tamy-status" :class="user.active ? 'is-active' : 'is-disabled'" x-text="user.active ? 'Active' : 'Disabled'"></span></div>
          <div class="tamy-user-actions">
            <select :value="user.role" @change="$store.tamyUsers.setRole(user, $event.target.value)"><option value="user">User</option><option value="superadmin">Super Admin</option></select>
            <button type="button" class="btn" @click="$store.tamyUsers.setActive(user, !user.active)" x-text="user.active ? 'Disable' : 'Enable'"></button>
            <input type="password" placeholder="New password" autocomplete="new-password" x-model="user.newPassword">
            <button type="button" class="btn" @click="$store.tamyUsers.resetPassword(user)">Reset password</button>
            <button type="button" class="btn tamy-danger" @click="$store.tamyUsers.deleteUser(user)">Delete</button>
          </div>
        </article>
      </template>
    </div>
  </section>
</body>
</html>
<style>
.tamy-users{display:grid;gap:1rem}.tamy-users-muted{margin:.35rem 0 0;color:var(--color-text-muted);max-width:58rem}.tamy-user-create{display:grid;grid-template-columns:1.2fr 1.4fr .9fr auto;gap:.65rem;padding:1rem;border:1px solid var(--color-border);border-radius:var(--border-radius-sm);background:var(--color-panel)}.tamy-user-create input,.tamy-user-create select,.tamy-user-actions input,.tamy-user-actions select{min-height:2.5rem;border:1px solid var(--color-border);border-radius:var(--border-radius-sm);background:var(--color-input);color:var(--color-text);padding:.55rem .7rem}.tamy-user-list{display:grid;gap:.7rem}.tamy-user-row{display:grid;gap:.8rem;padding:1rem;border:1px solid var(--color-border);border-radius:var(--border-radius-sm);background:var(--color-panel)}.tamy-user-identity,.tamy-user-actions{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap}.tamy-role-badge,.tamy-status{padding:.25rem .55rem;border-radius:999px;font-size:.75rem;border:1px solid var(--color-border)}.tamy-role-badge.role-superadmin{border-color:#d2a63c;color:#d2a63c}.tamy-status.is-active{color:#6fcf97}.tamy-status.is-disabled{color:var(--color-text-muted)}.tamy-user-actions input{min-width:10rem}.tamy-danger{color:var(--color-error-text)}@media(max-width:900px){.tamy-user-create{grid-template-columns:1fr}.tamy-user-actions{align-items:stretch;flex-direction:column}}
</style>
''')

sidebar = root / "webui/components/sidebar/top-section/header-icons.html"
sidebar_text = sidebar.read_text(encoding="utf-8")
sidebar_replacements = {
    '<button class="config-button header-action-button" id="header-plugins"': '<button x-show="globalThis.runtimeInfo?.isSuperAdmin" class="config-button header-action-button" id="header-plugins"',
    '<button class="config-button header-action-button" id="header-settings"': '<button x-show="globalThis.runtimeInfo?.isSuperAdmin" class="config-button header-action-button" id="header-settings"',
    '<button class="dropdown-item" @click="ensureModalOpen(\'settings/tunnel/remote-link.html\'); $store.sidebar.menuClose()">': '<button x-show="globalThis.runtimeInfo?.isSuperAdmin" class="dropdown-item" @click="ensureModalOpen(\'settings/tunnel/remote-link.html\'); $store.sidebar.menuClose()">',
    '<button class="dropdown-item" @click="openModal(\'settings/settings.html\'); $store.sidebar.menuClose()">': '<button x-show="globalThis.runtimeInfo?.isSuperAdmin" class="dropdown-item" @click="openModal(\'settings/settings.html\'); $store.sidebar.menuClose()">',
    '<button class="dropdown-item" @click="$confirmClick($event, () => { $store.chats.restart(); $store.sidebar.menuClose() })">': '<button x-show="globalThis.runtimeInfo?.isSuperAdmin" class="dropdown-item" @click="$confirmClick($event, () => { $store.chats.restart(); $store.sidebar.menuClose() })">',
}
for old, new in sidebar_replacements.items():
    if new not in sidebar_text:
        if old not in sidebar_text:
            raise SystemExit(f"Sidebar RBAC anchor not found: {old}")
        sidebar_text = sidebar_text.replace(old, new, 1)
sidebar.write_text(sidebar_text, encoding="utf-8")

write("tests/test_tamy_users.py", '''import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import tamy_users


class TamyUsersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "users.json"
        self.path_patch = patch.object(tamy_users, "_USERS_FILE", self.path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.tmp.cleanup()

    def test_first_user_is_superadmin_and_authenticates(self):
        user = tamy_users.create_user("admin", "password123", role="user")
        self.assertEqual(user["role"], "superadmin")
        self.assertIsNotNone(tamy_users.authenticate("admin", "password123"))
        self.assertNotIn("password_hash", tamy_users.list_users()[0])

    def test_wrong_password_fails(self):
        tamy_users.create_user("admin", "password123")
        self.assertIsNone(tamy_users.authenticate("admin", "wrong-password"))

    def test_last_superadmin_cannot_be_removed(self):
        tamy_users.create_user("admin", "password123")
        with self.assertRaises(ValueError): tamy_users.update_user("admin", role="user")
        with self.assertRaises(ValueError): tamy_users.update_user("admin", active=False)
        with self.assertRaises(ValueError): tamy_users.delete_user("admin")

    def test_second_admin_allows_role_change(self):
        tamy_users.create_user("admin", "password123")
        tamy_users.create_user("admin2", "password456", role="superadmin")
        self.assertEqual(tamy_users.update_user("admin", role="user")["role"], "user")

    def test_password_change_revokes_old_password(self):
        tamy_users.create_user("admin", "password123")
        tamy_users.update_user("admin", password="new-password123")
        self.assertIsNone(tamy_users.authenticate("admin", "password123"))
        self.assertIsNotNone(tamy_users.authenticate("admin", "new-password123"))


if __name__ == "__main__":
    unittest.main()
''')

for path in [
    "helpers/tamy_users.py", "helpers/login.py", "helpers/api.py", "helpers/ui_server.py",
    "api/tamy_users.py", "api/settings_get.py", "api/settings_set.py",
]:
    py_compile.compile(str(root / path), doraise=True)

print("Tamy RBAC patch prepared successfully")
