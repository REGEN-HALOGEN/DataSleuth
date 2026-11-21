# Render API and worker

## Free staging

The live staging deployment uses `render.staging.yaml` for the free API in
Singapore. It adopts the staging API by name and uses manual deploys. The
separate free Key Value instance requires internal authentication, with
external access blocked. The API's Docker startup script reads the
base64-encoded Supabase CA from `DATASLEUTH_DB_CA_B64` and writes it to
`/tmp/supabase-ca.crt`. Set the `sslrootcert` path in the runtime
`DATABASE_URL` to that file. The CA is a public certificate. Keep the
connection URL and its password in Render's server environment.

The worker and its authenticated Redis instance run in Docker on the WSL
host. They use separate Redis from the Render API. The worker discovers
queued jobs by polling PostgreSQL when it receives no Redis wake-up.
Keep the worker running during demos. If the worker stops, queued jobs
and document cleanup wait until it comes back.

## Separate hosted services

The `render.yaml` Blueprint defines two Docker services built from the same
backend directory. The image runs as a non-root Linux user.

| Service | Command | Initial size |
| --- | --- | --- |
| `datasleuth-api` | `python -m app.serve` | 1 CPU / 2 GB |
| `datasleuth-worker` | `python -m app.workers.scan` | 1 CPU / 2 GB |

Both services default to Oregon. Choose a region close to Supabase before
initial provisioning. The worker needs no inbound HTTP endpoint or persistent
disk. PostgreSQL stores jobs and results, and the bucket stores documents.
The API also runs bounded upload validation subprocesses. Benchmark both sizes with the synthetic corpus and concurrent login before
accepting additional load. [Render Blueprint reference](https://render.com/docs/blueprint-spec)

## Service settings

The Blueprint selects hosted mode, one process per service, and a 30-second
Render shutdown window. The API listens on Render's `PORT` and allows up to
20 seconds for graceful ASGI shutdown. It reads an exact HTTPS browser origin
from `BROWSER_ORIGIN`. Point that setting at the browser-facing frontend
origin. Serve `/api/v1/*` through that same origin and preserve `Origin`,
`Cookie` and `Set-Cookie`. Cookies are host-only, Secure, HttpOnly and
SameSite=Strict. The deployment model uses same-origin requests and exact
origin checks for mutations. Browser access from arbitrary origins is denied.

| Setting | Where to supply it |
| --- | --- |
| `DATABASE_URL` | Both services. Use the restricted runtime role and verified TLS. |
| `REDIS_URL` | Both services. Use one shared Redis-compatible instance per environment. |
| `SUPABASE_STORAGE_URL`, `SUPABASE_STORAGE_BUCKET`, `SUPABASE_STORAGE_KEY`, `UPLOAD_INTEGRITY_KEY` | Both services. Use identical private storage configuration. |
| `BROWSER_ORIGIN`, `APPLICATION_SECRET` | API only. Use a distinct random application secret of at least 32 characters. |
| `HMAC_KEY`, `HMAC_KEY_VERSION` | Worker only. Retain the key and version across releases. |
| `MIGRATION_DATABASE_URL` | One-off migration environment only. |

For Render Key Value, enable internal authentication and keep external access
disabled. Use the authenticated private `redis://` endpoint with a
`red-…` hostname on the same private network. An external Redis provider
requires an authenticated `rediss://` endpoint with certificate and hostname
verification. The worker polls PostgreSQL when wake-up notifications are
unavailable. Login throttling fails closed during Redis outages.
[Render Key Value setup](https://render.com/docs/key-value)

See [private storage settings](PRIVATE_STORAGE.md) and the
[database deployment guide](DEPLOYMENT_SUPABASE.md) for details. Hosted mode
accepts managed uploads and disables filesystem registration and claims.
Raw upload parsing still shares the service user with the parent process.
Use synthetic files for staging and validate stronger isolation before
accepting untrusted customer uploads.

## Release sequence

1. Prepare the Supabase runtime role, private Storage bucket, Redis and both
   services' environment settings. Keep credentials in server environments.
   Add the PostgreSQL CA file to each service when required by the chosen URL.
2. Use a trusted one-off environment built from the target source revision to
   run `python -m alembic upgrade head`, followed by `python -m alembic check`.
   Use the separately approved migration role. Coordinate migrations with
   existing service versions. Stop older writers before incompatible upgrades.
3. Deploy the API and worker from that revision. The Blueprint uses manual
   releases with no migration command attached to either service.
4. Check `/health` for process liveness and `/health/ready` for the expected
   Alembic revision, PostgreSQL connectivity and Redis connectivity. The worker
   also checks the schema at startup. The API readiness probe does not measure
   worker progress or test Storage on each request.
5. Bootstrap the first administrator through a trusted interactive terminal
   using `python -m app.manage_users --bootstrap-admin USERNAME`. Run it with
   the runtime DB settings and CA. Then run the synthetic upload, scan, review,
   export, deletion and restart workflow through the deployed browser.

A worker receiving SIGTERM interrupts active processing and attempts to relinquish
its lease. If shutdown interrupts that transaction, a replacement can recover the
job after lease expiry. Existing retry limits and stale-worker fencing govern
recovery. The API and worker startup logs contain allowlisted events. Protect
platform access logs and avoid capturing request bodies, cookies or credentials.

The free API was verified through the live Vercel browser workflow with
hosted Supabase and the WSL worker. The full paid API and worker Blueprint
was validated locally.
