# Security notes

## Local authentication

- Accounts are provisioned through `python -m app.manage_users` from a trusted
  terminal. The prompt refuses to fall back to visible password input. Passwords
  are stored as salted Argon2id hashes. The local administrator reset uses
  the same hidden terminal prompt and revokes that account's existing sessions.
- Sessions expire after eight hours. Logout and reauthentication revoke the
  presented session. PostgreSQL stores only digests of random session tokens.
  Cookies are host-only, `HttpOnly`, scoped to `/api/v1`, and
  `SameSite=Strict`. HTTPS origins enable `Secure`. The default local
  development origin uses loopback HTTP.
- Login and logout require the exact configured `BROWSER_ORIGIN`. The frontend
  serves the API under the same origin through the Vite proxy. Read-only API
  routes use session and role dependencies. Roles and account status are read
  from the database for each protected request.
- Redis throttles sign-in by account and globally. A Redis failure makes sign-in
  temporarily unavailable. The global limit is shared across users of this
  local instance.

## Logging and operational output

- Start the API with `python -m app.serve`. It installs the allowlisted JSON
  formatter before Uvicorn loads the application and disables access logging.
  Startup, auth validation, and dependency failures return generic diagnostics.
- Alembic hides bound parameters and suppresses chained SQLAlchemy exceptions
  when migrating. Use `alembic current` for the revision and
  `docker compose ps` for service health. Vite replaces proxy failure details
  with a fixed message.
- Compose, PostgreSQL, Redis, package tools, and debugger output are outside
  the app formatter. Use `docker compose config --quiet` to validate without
  printing resolved values. Keep raw service output and inspection data local.
  Redis authentication is supplied to the server as a process argument, which
  can be visible to Docker administrators. Keep diagnostic debug tracing off
  during authentication workflows.

## Local storage

- PostgreSQL and Redis bind to IPv4 loopback. Protect `.env` using Windows
  NTFS ACLs. POSIX mode bits on `/mnt/d` may differ from Windows permissions.
- Redis AOF and PostgreSQL use local persistent volumes. Use host-volume
  protection and backups appropriate to the data.
- Approved scan roots default to an empty list. Scanning is a later milestone.


## Organisation boundary

Each session references one membership. Protected requests resolve its role and
the active user from PostgreSQL. A browser-supplied organisation ID at login
must match a membership. The browser sends its expected organisation on data
requests so a stale tab cannot apply an action to a different organisation
after reauthentication. Membership removal cascades to matching sessions.

Tenant-owned parent/child relationships use composite foreign keys. The
application scopes aggregate queries, exports, review history, and worker
writes to the same organisation. New fingerprints use an HMAC-derived
organisation key. The local console, database credentials, worker process,
mount configuration, and HMAC master remain installation-wide trust boundaries.
Reserve root assignment and membership administration for the installation
operator. Application RBAC cannot isolate tenants from a database superuser or
an operator who exposes another organisation's files through a mount.
