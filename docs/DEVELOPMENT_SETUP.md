# Development setup

This is an early development foundation, not a complete application. Docker
Desktop and WSL 2 are prerequisites; Docker commands below were verified in
Ubuntu 24.04. The Windows CLI was not on PATH in the tested environment.

## Ubuntu

```bash
cd /mnt/d/WORK/PROJECTS/DataSleuth
python3 scripts/setup_env.py  # only on first setup; will not overwrite .env
python3 -m venv .venv-linux
.venv-linux/bin/python -m pip install -e './backend[dev]'
docker compose up -d
docker compose ps
cd backend
../.venv-linux/bin/alembic upgrade head
../.venv-linux/bin/python -m app.manage_users local-admin --role admin
../.venv-linux/bin/python -m app.serve
```

For manual WSL/Linux startup, start the scan worker in another terminal
from `backend`:

```bash
../.venv-linux/bin/python -m app.workers.scan
```

In a separate terminal, use a native Node installation for your platform.
From `frontend`, run `npm ci` and `npm run dev`. Open
`http://127.0.0.1:5173`. Windows and WSL require separate installations of
Node dependencies and Python virtual environments.

## Verification

From `backend`, run `../.venv-linux/bin/python -m pytest`,
`../.venv-linux/bin/ruff check .`, and `../.venv-linux/bin/ruff format --check .`.
The Windows equivalents use `..\.venv\Scripts\python.exe` and
`..\.venv\Scripts\ruff.exe`. From `frontend`, run `npm run lint`,
`npm run format`, and `npm run build`.

For backend integration tests, use disposable PostgreSQL and Redis instances
on loopback. Set `DATABASE_URL`, `POSTGRES_PASSWORD`, `REDIS_URL`, and
`REDIS_PASSWORD` for those instances and apply `alembic upgrade head`. Copy
those four settings to variables prefixed with `DATASLEUTH_TEST_` before
running pytest. Use a database with a `datasleuth_` prefix. The suite inserts
synthetic users and sessions and increments Redis counters. Pytest skips
database-backed checks when the four test settings are absent.

For browser tests, start the API and frontend against the disposable services.
Use the account command to create a synthetic administrator and viewer with
the same synthetic passphrase. Set `DATASLEUTH_E2E_ADMIN`,
`DATASLEUTH_E2E_VIEWER`, and `DATASLEUTH_E2E_PASSWORD` to match those accounts.
From `frontend`, run `npx playwright install chromium` and `npm test`.
The suite exercises the real browser, API, database, and session cookie.
To include the scan workflow, start the worker and set
`DATASLEUTH_E2E_SCAN_SOURCE` to an unregistered approved absolute directory
containing `synthetic.txt` with the same synthetic email address on two lines.
The default fixture value is `synthetic-browser-person@example.invalid`.
For repeat runs in the same disposable database, use a fresh directory and
a unique synthetic address, and set `DATASLEUTH_E2E_SCAN_VALUE` to the address.

For the multi-organisation browser test, give the synthetic admin a viewer membership in a second disposable organisation and set `DATASLEUTH_E2E_ORGANISATION` to its UUID. Keep its original local administrator membership.

Stop application processes with Ctrl+C and services with `docker compose stop`.
Do not use `docker compose down -v`: named volumes contain persistent data.
The scan worker supports WSL/Linux. Demo seeding is later work.
