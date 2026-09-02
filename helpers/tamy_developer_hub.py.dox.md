# tamy_developer_hub.py DOX

## Purpose

- Own the server-side GitHub synchronization service used by Tamy Developer Hub.
- Keep repository mutation fixed to the configured Tamy repository and branch.

## Ownership

- `get_state()` provides local Git state plus non-secret GitHub connection metadata.
- `connect_github()` and `disconnect_github()` manage the encrypted GitHub credential stored under ignored runtime state in `usr/`.
- `review_push()` creates a stale-safe review fingerprint for selected changed files.
- `push_reviewed()` stages only the reviewed files, commits them, and performs a non-force push.
- `pull_fast_forward()` and `sync_two_way()` perform fast-forward-only synchronization.
- `cleanup_repo()` runs non-destructive Git maintenance.

## Runtime Contracts

- Repository operations are locked to `TAMY_DEVELOPER_HUB_REPO`, defaulting to `mohamedamouseo-a11y/tamy`.
- Write operations are locked to `TAMY_DEVELOPER_HUB_BRANCH`, defaulting to `main`.
- The local Git top-level directory must be the Tamy source root and `origin` must match the configured repository before mutation.
- No force-push, reset, rebase, arbitrary shell command, or arbitrary repository path is exposed.
- Pull and sync refuse dirty worktrees; pull is fast-forward-only.
- Push requires a fresh review fingerprint and rejects remote-ahead/diverged history.
- Existing staged changes block Developer Hub push so unrelated staged content cannot be included accidentally.
- Sensitive paths and high-confidence secret patterns are rejected before staging.
- GitHub tokens are encrypted with a runtime key under ignored `usr/` state, never returned to the frontend, and are supplied to Git through environment-based HTTP headers rather than command-line URLs.
- Operation audit entries never contain credentials.

## Verification

- Run `pytest tests/test_tamy_developer_hub.py`.
- Run `python -m py_compile helpers/tamy_developer_hub.py api/tamy_developer_hub.py` after backend changes.
- Smoke-test Connect, Refresh, Review Push, Push, Pull, Sync, Disconnect, and dirty/diverged blocking against a disposable repository before production use.

## Child DOX Index

No child DOX files.
