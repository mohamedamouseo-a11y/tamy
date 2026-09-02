# tamy_users.py DOX

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
