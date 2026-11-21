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
`0002_auth` adds `users` and `browser_sessions`. Revision `0003_scan_sources`
adds `scan_sources` and `audit_events`. Revision `0004_scan_findings` adds
scan jobs, scanned-file metadata, fingerprints, and masked findings. Revision
`0005_scan_queue` adds job retry, lease, and cancellation data. Revision
`0006_finding_review` adds review status, reviewer, and review timestamps. Revision `0007_organisation_ownership` moves each existing role to a membership and binds historical data and sessions to the local organisation. Stop older writers and back up the database before the upgrade. See the local organisations section in the README. Run `upgrade head` to apply
the pending revisions. Use `alembic current` to verify which revision is applied. SQLAlchemy's session factory provides `sessions.begin()`
for commit/rollback and connection cleanup. Redis uses its client pool.

Changing `POSTGRES_PASSWORD` in `.env` does not update an initialized volume.
Use a deliberate database credential rotation procedure; never delete a volume
to repair an authentication error. Back up data before schema or credential
changes. `/health/ready` checks both services but not migration state.

Revision `0008_private_documents` adds nullable managed-document metadata and a storage consistency constraint to `scan_sources`. Existing directory rows preserve their paths. Downgrade to `0007` refuses to discard managed source history.
