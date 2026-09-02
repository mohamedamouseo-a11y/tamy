# tamy_users.py DOX

## Purpose
- Superadmin-only API for listing, creating, updating, disabling, promoting/demoting, password-resetting, and deleting Tamy users.

## Security
- The endpoint never returns password hashes, salts, or session tokens.
- `requires_superadmin()` enforces server-side authorization before the handler runs.
- User-store invariants prevent removal of the last active superadmin.
