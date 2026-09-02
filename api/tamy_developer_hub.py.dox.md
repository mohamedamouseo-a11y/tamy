# tamy_developer_hub.py DOX

## Purpose

- Expose the Super Admin-only HTTP entry point for Tamy Developer Hub.

## Request / Response Concepts

- Endpoint: `/api/tamy_developer_hub`.
- Supported methods: GET and POST.
- `action=state` returns local Git and connection metadata without a token.
- `action=connect|disconnect|branches|refresh` manages or verifies the GitHub connection.
- `action=review_push` returns a review fingerprint for selected changed files.
- `action=push` requires that fingerprint and revalidates it before mutation.
- `action=pull|sync|cleanup|logs` exposes the bounded service operations owned by `helpers/tamy_developer_hub.py`.

## Security Contracts

- Requires normal authenticated browser access, CSRF protection, and `requires_superadmin()` authorization.
- Raw GitHub tokens are accepted only for Connect and are never returned.
- The route does not accept repository roots, shell commands, force flags, or arbitrary branches.
- Expected service errors are returned as sanitized JSON with a stable error code.
- Unexpected exceptions are not returned to the browser.

## Verification

- Run `pytest tests/test_tamy_developer_hub.py`.
- Run `python -m py_compile helpers/tamy_developer_hub.py api/tamy_developer_hub.py`.
- Confirm a standard User receives HTTP 403 while a Super Admin can read the state.
