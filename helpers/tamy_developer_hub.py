from __future__ import annotations

import base64
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REPO = os.getenv("TAMY_DEVELOPER_HUB_REPO", "mohamedamouseo-a11y/tamy").strip()
ALLOWED_BRANCH = os.getenv("TAMY_DEVELOPER_HUB_BRANCH", "main").strip() or "main"
STATE_FILE = REPO_ROOT / "usr" / "tamy_developer_hub.json"
KEY_FILE = REPO_ROOT / "usr" / ".tamy_developer_hub.key"
MAX_SELECTED_FILES = 200
MAX_FILE_BYTES = 20 * 1024 * 1024
_LOCK = threading.RLock()

_BLOCKED_PATH_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_ed25519",
    "**/id_rsa",
    "**/id_ed25519",
    "usr/**",
    "tmp/**",
)

_SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("OpenAI-style secret", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)


class DeveloperHubError(RuntimeError):
    def __init__(self, message: str, status: int = 400, code: str = "developer_hub_error"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def _empty_state() -> dict[str, Any]:
    return {"version": 1, "github": {}, "operations": []}


def _load_state() -> dict[str, Any]:
    if not STATE_FILE.is_file():
        return _empty_state()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeveloperHubError("Developer Hub state is unreadable.", 500, "state_unreadable") from exc
    if not isinstance(data, dict):
        raise DeveloperHubError("Developer Hub state has an invalid format.", 500, "state_invalid")
    data.setdefault("version", 1)
    data.setdefault("github", {})
    data.setdefault("operations", [])
    return data


def _save_state(data: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    os.replace(temp, STATE_FILE)


def _get_fernet() -> Fernet:
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not KEY_FILE.is_file():
        key = Fernet.generate_key()
        temp = KEY_FILE.with_suffix(".tmp")
        temp.write_bytes(key)
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        os.replace(temp, KEY_FILE)
    try:
        key = KEY_FILE.read_bytes().strip()
        return Fernet(key)
    except (OSError, ValueError) as exc:
        raise DeveloperHubError("Developer Hub encryption key is unavailable.", 500, "key_unavailable") from exc


def _store_connection(token: str, user: dict[str, Any]) -> None:
    token = str(token or "").strip()
    if not token:
        raise DeveloperHubError("GitHub token is required.", 400, "token_required")
    encrypted = _get_fernet().encrypt(token.encode("utf-8")).decode("ascii")
    with _LOCK:
        data = _load_state()
        data["github"] = {
            "encrypted_token": encrypted,
            "user": str(user.get("login") or ""),
            "name": str(user.get("name") or ""),
        }
        _save_state(data)


def _read_token() -> str:
    with _LOCK:
        github = _load_state().get("github") or {}
        encrypted = str(github.get("encrypted_token") or "")
    if not encrypted:
        raise DeveloperHubError("Connect GitHub first.", 409, "github_not_connected")
    try:
        return _get_fernet().decrypt(encrypted.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise DeveloperHubError("Stored GitHub credentials cannot be decrypted. Reconnect GitHub.", 409, "token_invalid") from exc


def _connection_public() -> dict[str, Any]:
    with _LOCK:
        github = _load_state().get("github") or {}
    return {
        "connected": bool(github.get("encrypted_token")),
        "user": str(github.get("user") or ""),
        "name": str(github.get("name") or ""),
    }


def disconnect_github() -> None:
    with _LOCK:
        data = _load_state()
        data["github"] = {}
        _save_state(data)
    record_event("github_disconnect", "success", "GitHub connection removed")


def _github_request(token: str, path: str) -> Any:
    request = Request(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Tamy-Developer-Hub",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise DeveloperHubError("GitHub rejected the token or its permissions.", 403, "github_auth_failed") from exc
        if exc.code == 404:
            raise DeveloperHubError("The configured Tamy GitHub repository is not accessible with this token.", 404, "github_repo_unavailable") from exc
        raise DeveloperHubError("GitHub API request failed.", 502, "github_api_failed") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DeveloperHubError("Unable to reach GitHub right now.", 502, "github_unreachable") from exc


def connect_github(token: str) -> dict[str, Any]:
    token = str(token or "").strip()
    if not token:
        raise DeveloperHubError("GitHub token is required.", 400, "token_required")
    user = _github_request(token, "/user")
    _github_request(token, f"/repos/{EXPECTED_REPO}")
    _store_connection(token, user if isinstance(user, dict) else {})
    record_event("github_connect", "success", f"Connected GitHub as {str((user or {}).get('login') or 'unknown')}")
    return _connection_public()


def get_github_branches() -> list[dict[str, Any]]:
    token = _read_token()
    result = _github_request(token, f"/repos/{EXPECTED_REPO}/branches?per_page=100")
    if not isinstance(result, list):
        return []
    branches = []
    for item in result:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        branches.append({"name": name, "allowed": name == ALLOWED_BRANCH})
    return branches


def _sanitize_text(value: str, token: str | None = None) -> str:
    text = str(value or "")
    if token:
        text = text.replace(token, "[REDACTED]")
    text = re.sub(r"https://[^/@\s]+@github\.com/", "https://github.com/", text)
    return text[:4000]


def _run_git(args: list[str], *, token: str | None = None, check: bool = True, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LC_ALL"] = "C"
    if token:
        encoded = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        env["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {encoded}"
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeveloperHubError("Git command could not be completed.", 500, "git_unavailable") from exc
    if check and result.returncode != 0:
        detail = _sanitize_text(result.stderr.strip() or result.stdout.strip(), token)
        raise DeveloperHubError(detail or "Git command failed.", 409, "git_command_failed")
    return result


def _repo_from_origin(url: str) -> str:
    value = str(url or "").strip()
    if value.startswith("git@github.com:"):
        path = value.split(":", 1)[1]
    else:
        parsed = urlparse(value)
        if (parsed.hostname or "").lower() != "github.com":
            return ""
        path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path.strip("/")


def _safe_origin(url: str) -> str:
    value = str(url or "").strip()
    if value.startswith("git@github.com:"):
        return value
    parsed = urlparse(value)
    if not parsed.hostname:
        return value
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}{parsed.path}" if parsed.scheme else value


def _ensure_repo() -> None:
    inside = _run_git(["rev-parse", "--is-inside-work-tree"], check=False)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise DeveloperHubError("Tamy is not running from a Git working tree.", 409, "git_repo_missing")
    top = _run_git(["rev-parse", "--show-toplevel"]).stdout.strip()
    try:
        if Path(top).resolve() != REPO_ROOT.resolve():
            raise DeveloperHubError("Developer Hub is locked to the Tamy source repository root.", 409, "repo_root_mismatch")
    except OSError as exc:
        raise DeveloperHubError("Unable to validate the Tamy repository root.", 409, "repo_root_invalid") from exc


def _origin_url() -> str:
    return _run_git(["config", "--get", "remote.origin.url"]).stdout.strip()


def _current_branch() -> str:
    result = _run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _ensure_locked_context() -> None:
    _ensure_repo()
    origin_repo = _repo_from_origin(_origin_url())
    if origin_repo.casefold() != EXPECTED_REPO.casefold():
        raise DeveloperHubError(
            f"Developer Hub is locked to {EXPECTED_REPO}; the local origin does not match.",
            409,
            "origin_mismatch",
        )
    branch = _current_branch()
    if branch != ALLOWED_BRANCH:
        raise DeveloperHubError(
            f"Developer Hub write operations are locked to branch {ALLOWED_BRANCH}.",
            409,
            "branch_locked",
        )


def _github_git_url() -> str:
    return f"https://github.com/{EXPECTED_REPO}.git"


def _fetch_remote() -> None:
    _ensure_locked_context()
    token = _read_token()
    _run_git(
        [
            "fetch",
            "--prune",
            _github_git_url(),
            f"+refs/heads/{ALLOWED_BRANCH}:refs/remotes/origin/{ALLOWED_BRANCH}",
        ],
        token=token,
    )


def _remote_ref_exists() -> bool:
    result = _run_git(
        ["show-ref", "--verify", "--quiet", f"refs/remotes/origin/{ALLOWED_BRANCH}"],
        check=False,
    )
    return result.returncode == 0


def _ahead_behind() -> tuple[int, int]:
    if not _remote_ref_exists():
        return 0, 0
    output = _run_git(
        ["rev-list", "--left-right", "--count", f"HEAD...refs/remotes/origin/{ALLOWED_BRANCH}"]
    ).stdout.strip()
    try:
        ahead, behind = output.split()[:2]
        return int(ahead), int(behind)
    except (ValueError, IndexError):
        return 0, 0


def _normalize_repo_path(path: str) -> str:
    value = str(path or "").replace("\\", "/").strip()
    if not value or value.startswith("/") or "\x00" in value:
        raise DeveloperHubError("Invalid repository path.", 400, "invalid_path")
    candidate = (REPO_ROOT / value).resolve()
    try:
        candidate.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise DeveloperHubError("Repository path escapes the Tamy source root.", 400, "path_escape") from exc
    return value


def _parse_status() -> list[dict[str, Any]]:
    output = _run_git(["status", "--porcelain=v1", "-z", "--untracked-files=all"]).stdout
    tokens = output.split("\x00")
    changed: list[dict[str, Any]] = []
    index = 0
    while index < len(tokens):
        record = tokens[index]
        index += 1
        if not record:
            continue
        if len(record) < 4:
            continue
        xy = record[:2]
        path = _normalize_repo_path(record[3:])
        original_path = ""
        if "R" in xy or "C" in xy:
            if index < len(tokens) and tokens[index]:
                original_path = _normalize_repo_path(tokens[index])
                index += 1
        changed.append(
            {
                "path": path,
                "original_path": original_path,
                "status": xy,
                "staged": xy[0] not in (" ", "?"),
                "unstaged": xy[1] not in (" ", "?"),
                "untracked": xy == "??",
            }
        )
    return changed


def _head_sha() -> str:
    return _run_git(["rev-parse", "HEAD"]).stdout.strip()


def _remote_sha() -> str:
    if not _remote_ref_exists():
        return ""
    return _run_git(["rev-parse", f"refs/remotes/origin/{ALLOWED_BRANCH}"]).stdout.strip()


def _blocked_path_reason(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    for pattern in _BLOCKED_PATH_PATTERNS:
        if fnmatch.fnmatch(normalized, pattern):
            return f"Sensitive path is blocked: {path}"
    return None


def _snapshot_digest(path: str) -> str:
    normalized = _normalize_repo_path(path)
    target = REPO_ROOT / normalized
    if not target.exists():
        return hashlib.sha256(f"deleted:{normalized}".encode("utf-8")).hexdigest()
    if not target.is_file():
        raise DeveloperHubError(f"Only files can be pushed: {normalized}", 400, "not_a_file")
    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        raise DeveloperHubError(f"File is too large for Developer Hub review: {normalized}", 413, "file_too_large")
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _scan_file_for_secrets(path: str) -> list[str]:
    normalized = _normalize_repo_path(path)
    target = REPO_ROOT / normalized
    if not target.exists() or not target.is_file():
        return []
    if target.stat().st_size > MAX_FILE_BYTES:
        raise DeveloperHubError(f"File is too large for Developer Hub review: {normalized}", 413, "file_too_large")
    data = target.read_bytes()
    if b"\x00" in data[:8192]:
        return []
    text = data.decode("utf-8", errors="ignore")
    findings = []
    for label, pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(f"Possible {label} found in {normalized}")
    return findings


def _diff_stats(path: str, untracked: bool) -> dict[str, int]:
    if untracked:
        target = REPO_ROOT / path
        if not target.is_file():
            return {"added": 0, "deleted": 0}
        try:
            text = target.read_text(encoding="utf-8", errors="ignore")
            return {"added": len(text.splitlines()), "deleted": 0}
        except OSError:
            return {"added": 0, "deleted": 0}
    result = _run_git(["diff", "--numstat", "HEAD", "--", path], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return {"added": 0, "deleted": 0}
    line = result.stdout.splitlines()[0]
    parts = line.split("\t")
    if len(parts) < 2:
        return {"added": 0, "deleted": 0}
    try:
        added = int(parts[0]) if parts[0] != "-" else 0
        deleted = int(parts[1]) if parts[1] != "-" else 0
    except ValueError:
        added = deleted = 0
    return {"added": added, "deleted": deleted}


def _validate_selected(paths: list[str], changes: list[dict[str, Any]]) -> list[str]:
    if not isinstance(paths, list):
        raise DeveloperHubError("Selected files must be a list.", 400, "invalid_selection")
    unique: list[str] = []
    seen: set[str] = set()
    available = {item["path"] for item in changes}
    for raw in paths:
        path = _normalize_repo_path(str(raw))
        if path in seen:
            continue
        if path not in available:
            raise DeveloperHubError(f"Selected file is no longer changed: {path}", 409, "stale_selection")
        reason = _blocked_path_reason(path)
        if reason:
            raise DeveloperHubError(reason, 403, "sensitive_path")
        unique.append(path)
        seen.add(path)
    if len(unique) > MAX_SELECTED_FILES:
        raise DeveloperHubError("Too many files selected for one push.", 400, "too_many_files")
    return sorted(unique)


def _validate_commit_message(message: str, has_selected_files: bool) -> str:
    value = str(message or "").strip()
    if not has_selected_files:
        return value
    if len(value) < 3:
        raise DeveloperHubError("Enter a commit message before reviewing the push.", 400, "commit_message_required")
    if len(value) > 160:
        raise DeveloperHubError("Commit message is too long.", 400, "commit_message_too_long")
    if "\n" in value or "\r" in value:
        raise DeveloperHubError("Commit message must be one line.", 400, "commit_message_invalid")
    return value


def _ensure_clean_staging(changes: list[dict[str, Any]]) -> None:
    staged = [item["path"] for item in changes if item.get("staged")]
    if staged:
        raise DeveloperHubError(
            "Developer Hub found pre-existing staged changes. Commit or unstage them outside the Hub first.",
            409,
            "staging_not_clean",
        )


def _prepare_review(paths: list[str], message: str, *, fetch_remote: bool) -> dict[str, Any]:
    _ensure_locked_context()
    _read_token()
    if fetch_remote:
        _fetch_remote()
    changes = _parse_status()
    _ensure_clean_staging(changes)
    ahead, behind = _ahead_behind()
    if ahead and behind:
        raise DeveloperHubError("Local and GitHub history have diverged. Automatic push is blocked.", 409, "history_diverged")
    if behind:
        raise DeveloperHubError("GitHub is ahead. Pull the latest changes before pushing.", 409, "remote_ahead")

    selected = _validate_selected(paths, changes)
    message = _validate_commit_message(message, bool(selected))
    if not selected and ahead == 0:
        raise DeveloperHubError("There is nothing ready to push.", 409, "nothing_to_push")

    change_map = {item["path"]: item for item in changes}
    findings: list[str] = []
    files: list[dict[str, Any]] = []
    snapshots: list[dict[str, str]] = []
    for path in selected:
        findings.extend(_scan_file_for_secrets(path))
        item = change_map[path]
        digest = _snapshot_digest(path)
        snapshots.append({"path": path, "digest": digest})
        files.append(
            {
                "path": path,
                "status": item["status"],
                "stats": _diff_stats(path, bool(item.get("untracked"))),
            }
        )
    if findings:
        raise DeveloperHubError("Secret scan blocked this push: " + "; ".join(findings[:5]), 403, "secret_scan_failed")

    payload = {
        "repo": EXPECTED_REPO,
        "branch": ALLOWED_BRANCH,
        "head": _head_sha(),
        "remote_head": _remote_sha(),
        "ahead": ahead,
        "message": message,
        "files": snapshots,
    }
    review_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "review_id": review_id,
        "repo": EXPECTED_REPO,
        "branch": ALLOWED_BRANCH,
        "head": payload["head"],
        "remote_head": payload["remote_head"],
        "ahead": ahead,
        "behind": behind,
        "commit_message": message,
        "files": files,
        "selected_count": len(selected),
        "existing_commits_only": not selected and ahead > 0,
    }


def review_push(paths: list[str], message: str) -> dict[str, Any]:
    review = _prepare_review(paths, message, fetch_remote=True)
    record_event("review_push", "success", f"Reviewed {review['selected_count']} file(s) for {EXPECTED_REPO}:{ALLOWED_BRANCH}")
    return review


def push_reviewed(paths: list[str], message: str, review_id: str) -> dict[str, Any]:
    supplied = str(review_id or "").strip()
    if not supplied:
        raise DeveloperHubError("Review the push before sending it to GitHub.", 409, "review_required")
    with _LOCK:
        review = _prepare_review(paths, message, fetch_remote=True)
        if review["review_id"] != supplied:
            raise DeveloperHubError("The reviewed files changed. Review the push again.", 409, "review_stale")
        selected = [item["path"] for item in review["files"]]
        token = _read_token()
        commit_sha = ""
        if selected:
            try:
                _run_git(["add", "--", *selected])
                staged_check = _run_git(["diff", "--cached", "--quiet"], check=False)
                if staged_check.returncode == 0:
                    _run_git(["reset", "--", *selected], check=False)
                    raise DeveloperHubError("Selected files produced no staged changes.", 409, "nothing_staged")
                _run_git(["commit", "-m", review["commit_message"]])
                commit_sha = _head_sha()
            except Exception:
                _run_git(["reset", "--", *selected], check=False)
                raise
        _run_git(
            ["push", _github_git_url(), f"HEAD:refs/heads/{ALLOWED_BRANCH}"],
            token=token,
            timeout=120,
        )
        _fetch_remote()
    detail = f"Pushed {commit_sha[:12] if commit_sha else 'existing commits'} to {EXPECTED_REPO}:{ALLOWED_BRANCH}"
    record_event("push", "success", detail)
    return {"ok": True, "commit": commit_sha, "state": get_state()}


def pull_fast_forward() -> dict[str, Any]:
    with _LOCK:
        _ensure_locked_context()
        _read_token()
        if _parse_status():
            raise DeveloperHubError("Pull is blocked while the working tree has local changes.", 409, "dirty_worktree")
        _fetch_remote()
        ahead, behind = _ahead_behind()
        if ahead and behind:
            raise DeveloperHubError("Local and GitHub history have diverged. Fast-forward pull is blocked.", 409, "history_diverged")
        if ahead:
            raise DeveloperHubError("Local commits are ahead of GitHub. Push them before pulling.", 409, "local_ahead")
        if behind:
            _run_git(["merge", "--ff-only", f"refs/remotes/origin/{ALLOWED_BRANCH}"])
    record_event("pull", "success", f"Fast-forwarded {behind} commit(s) from GitHub")
    return {"ok": True, "state": get_state()}


def sync_two_way() -> dict[str, Any]:
    with _LOCK:
        _ensure_locked_context()
        token = _read_token()
        if _parse_status():
            raise DeveloperHubError("Sync is blocked while the working tree has local changes. Review and push them first.", 409, "dirty_worktree")
        _fetch_remote()
        ahead, behind = _ahead_behind()
        if ahead and behind:
            raise DeveloperHubError("Local and GitHub history have diverged. Automatic sync is blocked.", 409, "history_diverged")
        pulled = 0
        pushed = 0
        if behind:
            _run_git(["merge", "--ff-only", f"refs/remotes/origin/{ALLOWED_BRANCH}"])
            pulled = behind
        ahead_after, behind_after = _ahead_behind()
        if behind_after:
            raise DeveloperHubError("GitHub moved during sync. Refresh and try again.", 409, "remote_changed")
        if ahead_after:
            _run_git(
                ["push", _github_git_url(), f"HEAD:refs/heads/{ALLOWED_BRANCH}"],
                token=token,
                timeout=120,
            )
            pushed = ahead_after
            _fetch_remote()
    record_event("sync", "success", f"Sync complete: pulled {pulled}, pushed {pushed}")
    return {"ok": True, "pulled": pulled, "pushed": pushed, "state": get_state()}


def cleanup_repo() -> dict[str, Any]:
    with _LOCK:
        _ensure_locked_context()
        _run_git(["gc", "--auto"], timeout=120)
    record_event("cleanup", "success", "Git maintenance completed")
    return {"ok": True, "state": get_state()}


def record_event(action: str, status: str, detail: str) -> None:
    event = {
        "action": str(action or "")[:80],
        "status": "success" if status == "success" else "error",
        "detail": _sanitize_text(str(detail or ""))[:500],
    }
    try:
        with _LOCK:
            data = _load_state()
            operations = list(data.get("operations") or [])
            operations.append(event)
            data["operations"] = operations[-200:]
            _save_state(data)
    except Exception:
        # Git operations must not be reported as failed only because audit persistence failed.
        pass


def get_operations(limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK:
        operations = list(_load_state().get("operations") or [])
    return operations[-max(1, min(int(limit), 200)):][::-1]


def get_state(*, fetch_remote: bool = False) -> dict[str, Any]:
    connection = _connection_public()
    state: dict[str, Any] = {
        "repo": EXPECTED_REPO,
        "allowed_branch": ALLOWED_BRANCH,
        "connection": connection,
        "repo_available": False,
        "origin": "",
        "origin_matches": False,
        "branch": "",
        "head": "",
        "remote_head": "",
        "ahead": 0,
        "behind": 0,
        "dirty": False,
        "changed_files": [],
        "operations": get_operations(),
        "write_ready": False,
        "error": "",
    }
    try:
        _ensure_repo()
        origin = _origin_url()
        branch = _current_branch()
        origin_matches = _repo_from_origin(origin).casefold() == EXPECTED_REPO.casefold()
        if fetch_remote:
            _ensure_locked_context()
            _read_token()
            _fetch_remote()
        changed = _parse_status()
        ahead, behind = _ahead_behind()
        state.update(
            {
                "repo_available": True,
                "origin": _safe_origin(origin),
                "origin_matches": origin_matches,
                "branch": branch,
                "head": _head_sha(),
                "remote_head": _remote_sha(),
                "ahead": ahead,
                "behind": behind,
                "dirty": bool(changed),
                "changed_files": changed,
                "write_ready": bool(
                    connection["connected"]
                    and origin_matches
                    and branch == ALLOWED_BRANCH
                ),
            }
        )
    except DeveloperHubError as exc:
        state["error"] = exc.message
    return state
