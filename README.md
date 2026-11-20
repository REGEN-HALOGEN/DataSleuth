# DataSleuth

DataSleuth is a local-first privacy discovery application under development.
The local foundation includes account sign-in and role-based access. The scanner foundation supports approved sources and a read-only backend pipeline that stores masked findings.
See [implementation status](Project_Docs/IMPLEMENTATION_STATUS.md) and the
specifications in `Project_Docs/`.

## Prerequisites

Windows 11 with WSL 2 Ubuntu, Docker Desktop with Ubuntu integration, Python
3.12 and Node/npm. The services have been verified from Ubuntu; Windows Docker
CLI was not available on PATH. Install Node and frontend dependencies on the same platform. Use the loopback
addresses shown below for local development.

## Quick start from WSL

Start Docker Desktop with WSL integration enabled. With Python 3.12+, Node.js,
npm, and curl available in WSL, run this from the project root:

```bash
bash start.sh
```

The script prepares the Linux dependencies, starts PostgreSQL and Redis,
applies pending migrations, and runs the API, frontend, and scan worker. The API and frontend bind to loopback. When
there is no active administrator, it prompts for a username and a hidden
passphrase of 10–256 characters. Press Enter at the username prompt to use `local-admin`. There is
no preset password. Sign in at `http://127.0.0.1:5173` with the credentials you
just chose. Subsequent runs reuse your existing accounts.

To try a scan, set `ALLOWED_SCAN_ROOTS` in the local `.env` to a JSON list
of approved absolute WSL paths and restart the app. Open **Scan Sources**,
register an approved directory, and confirm a read-only scan. **Scan History**
shows live counts and lets operators cancel queued or running scans.
Open **Discoveries** to filter masked findings, review individual results,
and inspect related occurrences.

Keep the terminal open while using DataSleuth. Ctrl+C stops the API, frontend, and
scan worker. Run `docker compose stop` separately to stop PostgreSQL and Redis.
The script preserves existing frontend dependency directories under
`.venv-linux/frontend-deps.*` when switching to a fresh WSL installation.
Run frontend setup with Windows npm again if you switch back to Windows.

## Manual setup

In PowerShell at the project root:

```powershell
python scripts/setup_env.py
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
Set-Location frontend
npm ci
Set-Location ..
```

The setup script creates `.env` with independent random secrets and refuses to
overwrite an existing file. The default approved scan roots are empty.
Protect `.env` using Windows file permissions; never commit or share it. The
PostgreSQL password is only applied when a new database volume is initialized;
changing `.env` later does not change an existing database password.

Start services from Ubuntu:

```bash
cd /mnt/d/WORK/PROJECTS/DataSleuth
docker compose up -d
docker compose ps
```

Run migrations and start the backend from PowerShell:

```powershell
Set-Location backend
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\python.exe -m app.manage_users local-admin --role admin
..\.venv\Scripts\python.exe -m app.serve
```

The account command prompts for a passphrase of 15–256 characters with hidden
input. Run it once per account. Supported roles are `admin`, `analyst`, and
`viewer`. All active roles can sign in. Administrators can view Accounts.

Start the frontend in another PowerShell window:

```powershell
Set-Location D:\WORK\PROJECTS\DataSleuth\frontend
npm run dev
```

Open `http://127.0.0.1:5173` and sign in. The frontend proxies API requests
through the same browser origin. The default allowed origin is
`http://127.0.0.1:5173`.

`http://127.0.0.1:8000/health` checks the process; `/health/ready` tests
PostgreSQL and Redis. Stop frontend and backend with Ctrl+C. In Ubuntu, run
`docker compose stop` from the project root to stop services without removing
containers or volumes.

## Tests and troubleshooting

From `backend`, run `..\.venv\Scripts\python.exe -m pytest` and
`..\.venv\Scripts\ruff.exe check .`. From `frontend`, run `npm run lint`, `npm run format`, and `npm run build`.
For database-backed API and browser tests, see [development setup](docs/DEVELOPMENT_SETUP.md).
See [development setup](docs/DEVELOPMENT_SETUP.md),
[database setup](docs/DATABASE_SETUP.md), and
[security notes](docs/SECURITY_NOTES.md) for Ubuntu commands and limitations.
If services are unhealthy, inspect `docker compose ps` and sanitized service
logs; ensure Docker Desktop is running and ports 5432 and 6379 are free.
Never paste `.env`, resolved `docker compose config`, or connection URLs into
logs or bug reports.


## Changelog

Update this section in the same commit or pull request as any user-visible
feature, fix, setup change, or security change. Keep entries newest first and
record any migration or action required by existing users. After verifying
each completed task, review the staged files for sensitive data, commit the
changes, and push the commit to GitHub before starting the next objective.

### 2026-11-20 — Operational overview

- Added live overview totals, recent scans, finding categories, and a link
  to findings awaiting review. Metrics come from stored scanner and review
  data.

### 2026-11-20 — Findings inventory and review

- Added Discoveries with paginated, filterable masked findings and links from
  Scan History to scan-specific results.
- Added persistent review status and audit history, and related-occurrence
  tables for findings that share a versioned fingerprint.
- Added migration `0006_finding_review`. Existing findings default to
  **Needs review**. WSL startup applies the migration automatically.

### 2026-11-20 — Browser scan workflow

- Added protected Scan Sources and Scan History screens for administrators
  and analysts. Operators can manage approved directories, confirm scan
  launches, follow persisted progress, and cancel jobs.
- Verified a full browser scan against the running worker, including source
  registration, enable/disable, rename, and actual finding counts.

### 2026-11-20 — Background scan processing

- Added authenticated scan launch, status, history, and cancellation endpoints
  under `/api/v1/scans`. Launches require an enabled source ID and explicit
  read-only confirmation.
- The WSL/Linux worker uses Redis notifications and durable PostgreSQL jobs.
  Interrupted scans resume pending files with up to three worker attempts.
  Cancelling a scan keeps committed results and discards in-flight output.
- `start.sh` now runs the worker and applies migration `0005_scan_queue`.
  Start the worker separately with `python -m app.workers.scan` for a manual
  WSL/Linux setup.

### 2026-11-20 — Bounded readers and masked findings

- Added WSL/Linux readers for TXT, LOG, CSV, JSON, text-based PDF, XLSX, and
  XLSM. Extraction runs in a separate process with input, output, memory, and
  time limits. Spreadsheet macros and formulas are never executed.
- Added deterministic potential-match detection for email, Indian mobile
  numbers, PAN-shaped and Aadhaar-shaped values, IFSC, and context-labelled
  bank account numbers. Stored evidence is redacted and duplicates correlate
  through versioned HMAC fingerprints.
- Added migration `0004_scan_findings` and verified the pipeline with synthetic
  files and disposable PostgreSQL. `bash start.sh` refreshes dependencies and
  applies the migration. Manual setup requires reinstalling backend
  dependencies and running `alembic upgrade head`.
- The pipeline is available to trusted backend code. Scan launch, progress,
  cancellation, and findings views were pending at this checkpoint.

### 2026-11-20 — Scanner foundation begins

- Added authenticated API endpoints to register, list, inspect, rename, enable,
  and disable local directory sources. Source changes are audited.
- Added bounded metadata-only file discovery for WSL/Linux. It skips symlinks
  and enforces configured depth, entry count, and file-size limits.
- Added migration `0003_scan_sources`. Run `bash start.sh` on WSL or
  `alembic upgrade head` during manual setup. Configure `ALLOWED_SCAN_ROOTS`
  as a JSON list of approved absolute paths before registering a source.

### 2026-11-20 — Milestone 0 foundation

- Added local sign-in, sign-out, and session restoration with Argon2id password
  hashing, expiring sessions, login throttling, and server-side role checks.
- Added an administrator-only Accounts view and the `0002_auth` schema migration.
- Added `start.sh` for WSL. It starts the stack, applies migrations, and prompts
  for the first administrator with a hidden 10–256 character passphrase.
- Hardened startup, migration, and proxy diagnostics against sensitive output.
- Verified database migrations, backend authentication, and browser sign-in.
