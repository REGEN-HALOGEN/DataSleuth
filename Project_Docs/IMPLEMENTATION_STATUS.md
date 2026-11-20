# Implementation status

Last updated: 2026-11-20

## Milestones

- [x] **0 — Foundation:** localhost infrastructure, validated configuration, pooled connections, migrations, health endpoints, fail-closed logging, local account provisioning, authentication, server-side RBAC, protected frontend routes, and automated verification.
- [ ] **1 — Safe source and scanner foundation:** pending.
- [ ] **2 — Detection and privacy protections:** pending.
- [ ] **3 — Inventory and analyst workflow:** pending.
- [ ] **4 — Reporting and demonstration:** pending.

## Next phase

Start with the scanner phase in the engineering handover. Build and verify
read-only discovery of operator-approved directories, bounded readers for the
formats in the scope, and the initial detection, masking, keyed fingerprinting,
and findings persistence. The first tests should cover path traversal, symlink
escapes, and unsupported, oversized, or malformed inputs using synthetic files.

Background processing follows the scanner phase. Keep the safe scanner
milestone open until the scope's worker, progress, and cancellation criteria
are verified. The milestone labels above follow the scope document.

## Milestone 0 implementation

- Alembic revision `0002_auth` creates users and browser sessions. The provisioning command supports admin, analyst, and viewer roles and reads passphrases through a hidden terminal prompt.
- Passwords use Argon2id. Sessions expire after eight hours and store only token digests. Login rotates the presented session. Logout revokes it. Redis throttles sign-in, and the API checks current roles and account status for protected requests.
- The browser uses a same-origin API proxy, strict HttpOnly session cookies, and exact-origin checks for login and logout. React Router protects Overview and Accounts. Accounts is an admin-only view backed by the API.
- The API launcher configures fail-closed logging before application import. Startup and validation errors use fixed diagnostics. Alembic suppresses chained database errors, and the Vite proxy redacts failure details. External tool output is covered in [security notes](../docs/SECURITY_NOTES.md).
- The foundation retains the existing CSS and uses native form handling and a small typed fetch client for the two authentication screens. Adopt additional frontend libraries when the relevant workflows need them.

## Verification

- WSL Python 3.12.3 and Windows Python 3.12.10 each passed 14 backend tests against disposable PostgreSQL and Redis instances. One Starlette/AnyIO deprecation warning remains.
- Ruff lint and formatting checks passed. ESLint, Prettier, and TypeScript checks passed, and Vite production builds completed on Windows and WSL with platform-native dependencies. The frontend dependency audit found zero advisories at verification time.
- Four Chromium tests passed against the live frontend and API. They exercised direct route protection, invalid credentials, session restoration, role denial, sign-out, and redirect after loss of the session.
- Both fresh-to-head and baseline-to-head PostgreSQL migration paths reached `0002_auth`. Alembic detected no schema drift. An intentionally failed connection produced the generic migration diagnostic without the synthetic marker.
- The live `/health` and `/health/ready` endpoints returned HTTP 200. PostgreSQL and Redis reported healthy on loopback. Compose configuration validated without printing resolved values. A forced Vite proxy failure logged a fixed message without the synthetic URL marker.

## Limitations

- Account provisioning is add-only and local. The WSL startup script prompts for the first administrator when needed. The default development browser origin uses loopback HTTP.
- Start with `bash start.sh` on WSL to apply pending migrations automatically, or run `alembic upgrade head` during manual setup. Migration verification used disposable databases.
- Scanner, worker, and analyst workflows remain pending. Milestone 0 covers the local application foundation.
