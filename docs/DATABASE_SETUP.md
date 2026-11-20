# Database and Redis

Compose starts PostgreSQL 17 and Redis 8 on `127.0.0.1` ports 5432 and 6379.
Both use named volumes. Redis authentication and append-only persistence are
enabled. `docker compose ps` shows service health.

On Windows PowerShell, from `backend`:

```powershell
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\alembic.exe current
```

On Ubuntu, from `backend`:

```bash
../.venv-linux/bin/alembic upgrade head
../.venv-linux/bin/alembic current
```

The initial `0001_baseline` migration is intentionally empty. Revision
`0002_auth` adds `users` and `browser_sessions`. Run `upgrade head` to apply
the pending revisions. Use `alembic current` to verify which revision is applied. SQLAlchemy's session factory provides `sessions.begin()`
for commit/rollback and connection cleanup. Redis uses its client pool.

Changing `POSTGRES_PASSWORD` in `.env` does not update an initialized volume.
Use a deliberate database credential rotation procedure; never delete a volume
to repair an authentication error. Back up data before schema or credential
changes. `/health/ready` checks both services but not migration state.
