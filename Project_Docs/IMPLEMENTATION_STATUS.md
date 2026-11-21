# Implementation status

Last updated: 2026-11-21

## Vercel frontend preparation — 2026-11-21

The Vercel configuration builds the Vite frontend and rewrites relative
`/api/v1/*` requests to an HTTPS Render origin supplied at build time.
It disables API caching and handles React Router deep links. Local checks
validated the generated Vercel configuration, API route matching, frontend
fallback and rejection of invalid origins. The Vite production build and
frontend lint and formatting checks passed. Six Chromium tests passed
through the local preview proxy. The private-upload browser test was
skipped in this run and previously passed in the storage increment.

The hosted proxy, cookie forwarding and maximum upload size still require
a staging browser run. [Vercel runbook](../docs/DEPLOYMENT_VERCEL.md)

## Hosted API and worker preparation — 2026-11-21

The Render Blueprint defines separate Docker services for the API and
persistent worker. Hosted mode disables local filesystem claims and requires
a private Storage configuration, verified PostgreSQL TLS, authenticated
Redis and an exact HTTPS frontend origin for the API. The API and worker use
separate database pool limits and secret requirements. Alembic uses a
separate migration connection. The API readiness probe checks PostgreSQL,
the expected Alembic revision and Redis. The worker checks schema
compatibility before claiming jobs.

| Local verification | Result |
| --- | --- |
| Render Blueprint and image | Blueprint validated against Render's published JSON Schema. The Docker image built and the non-root runtime executed the isolated parser. |
| Hosted Docker smoke | Verified PostgreSQL TLS and authenticated Redis over the disposable private network. The API returned 503 before migration and during a Redis outage, and recovered in both cases. The worker refused the empty schema and left a queued directory job untouched after migration. The API rejected a foreign origin and set Secure, HttpOnly, SameSite=Strict cookies. Both containers exited successfully on SIGTERM. |
| Backend regression suite | 59 passed against disposable PostgreSQL, Redis and self-hosted Supabase Storage. Coverage includes active lease release and resume, storage regression and local synthetic acceptance. The existing Starlette/AnyIO deprecation warning remains. |

Hosted provider connectivity, platform proxy behaviour and parser sandboxing
for untrusted customer uploads remain staging work. The next deployment
increment is the Vercel same-origin frontend proxy and browser verification.
[Render runbook](../docs/DEPLOYMENT_RENDER.md) · [Supabase runbook](../docs/DEPLOYMENT_SUPABASE.md)

## Storage adapters and private document sources — 2026-11-21

The scanner now inventories and opens bounded inputs through local-directory
and private-document adapters. The existing durable queue, parser subprocess,
detectors, review workflow and reports serve both. Each managed source owns one
immutable document. The API reserves quota and accepts authenticated binary
uploads. The worker verifies size and a source-specific keyed digest before
parsing. Expiry and explicit deletion retain masked findings and audit history.

| Local verification on WSL/Linux | Result |
| --- | --- |
| Local adapter before adding the private adapter | All 39 existing backend tests passed, including the original synthetic acceptance, cancellation and stale-worker cases. |
| Empty database and populated `0007` upgrade | Reached `0008_private_documents` and Alembic reported no drift. An independent before/after check verified every existing field on a legacy directory source. |
| Complete backend suite | 46 passed against fresh and upgraded disposable PostgreSQL 17 databases, with Redis 8 and a self-hosted Supabase Storage v1.89.12 REST service. The existing Starlette/AnyIO warning remains. |
| Storage operations | All seven file formats scanned. Tests covered cross-tenant access, write-once publication, quota and input validation, changed bytes, scratch cleanup, lost upload responses, stale claims, deletion retry, expiry and preserved reports. Public, unauthenticated and anonymous-role reads were denied by the local provider. A public test bucket failed the privacy check. |
| Frontend and browser | Production build, ESLint and Prettier passed. Seven Chromium tests passed through the live API, worker and preview proxy, including a private upload, scan and deletion request. |
| Backend static checks | Ruff lint and formatting passed. |

The standalone local Storage service used its filesystem backend and a test
service-role JWT. Hosted Supabase gateway credentials, deployed bucket policies,
provider backup retention, and Render/Vercel deployment still require staging
verification. The next deployment increment is API and worker production
configuration. [Storage setup and lifecycle](../docs/PRIVATE_STORAGE.md)

## Tenant-safe local increment — 2026-11-20

Implemented organisation memberships and membership-bound sessions, tenant
ownership checks throughout the API and worker, organisation-specific local
root grants, and tenant-separated HMAC fingerprints. Trusted console tools
manage membership. The browser displays the active organisation and supports
sign-in to a specific organisation. See [local setup and upgrade](../README.md#local-organisations).

| Verification on WSL/Linux | Result |
| --- | --- |
| Unchanged baseline at `033b287`, isolated PostgreSQL 17 and Redis 8 | 35 backend tests and 5 Chromium tests passed, including real-worker synthetic scan, review, export, and restart. Production Vite build passed. |
| Empty database to `0007_organisation_ownership` | All revisions applied. Alembic reported no schema drift. |
| Populated `0006_finding_review` to head | Before/after comparison preserved 38 identities and password hashes, 21 session rows, 9 sources, 11 jobs, 27 file rows, 7 fingerprints, 18 findings and 31 audits. All original roles matched the backfilled memberships. |
| Compatibility after upgrade | An existing cookie authenticated. A partially processed job resumed with its original scheme and added two occurrences to its existing group. Alembic reported no drift. |
| Backend regression and synthetic acceptance | 39 tests passed on both fresh and upgraded databases. The synthetic workflow verified nine file outcomes, six masked findings, related occurrences, review history, both export formats, and restart persistence. |
| Browser and frontend | Six Chromium tests passed through an isolated loopback Vite preview proxy, including the full worker scan and a user with different roles in two organisations. TypeScript, Vite production build, ESLint and Prettier checks passed. |
| Backend static checks | Ruff lint and formatting passed. Pytest reports the existing Starlette/AnyIO deprecation warning. |

Isolation tests covered foreign UUID reads and writes, search, aggregates,
directory registration, account lists, both report formats, fingerprint
separation on identical input, invalid cross-organisation database references,
and membership revocation during parsing. Each synthetic acceptance run now
uses an independent organisation so repeated fixtures keep deterministic
related-occurrence counts on a reused disposable database.

The local filesystem, process and database administrators remain trusted.
Operators control disjoint roots and worker assignments. Native Windows
worker execution and cloud storage/deployment are unverified. No hosted
services or production databases participated in this increment.

## Milestones

- [x] **0 — Foundation:** localhost infrastructure, validated configuration, pooled connections, migrations, health endpoints, fail-closed logging, local account provisioning, authentication, server-side RBAC, protected frontend routes, and automated verification.
- [x] **1 — Safe source and scanner foundation:** source API, bounded scanner, persisted jobs, WSL/Linux worker, retries, and cancellation verified.
- [ ] **2 — Detection and privacy protections:** deterministic detectors, masked evidence, and analyst access to versioned correlation are implemented and verified.
- [x] **3 — Inventory and analyst workflow:** source management, scan history, findings inventory, audited review, related-occurrence tables, and operational overview are implemented and verified.
- [x] **4 — Reporting and demonstration:** masked CSV/JSON exports and the reproducible WSL synthetic acceptance workflow are implemented and verified.

## Scanner foundation progress

- Migration `0003_scan_sources` adds persistent sources and audit events.
  Administrators and analysts can register, list, inspect, rename, enable,
  and disable sources through `/api/v1/sources`. The API rejects paths outside
  `ALLOWED_SCAN_ROOTS` and revalidates a source when it is enabled.
- WSL/Linux discovery inventories metadata within a validated directory.
  Descriptor-relative traversal rejects symlinks, including a source path
  swapped after validation. Discovery bounds entries examined, recursion depth,
  and eligible file size.
- Verified 18 backend tests against disposable PostgreSQL and Redis.
  Migration from `0002_auth` to `0003_scan_sources` succeeded and Alembic
  reported no schema drift.

## Readers and findings progress

- The WSL/Linux pipeline revalidates approved sources and opens only regular,
  single-link files using descriptor-relative reads. Extraction uses an
  isolated Python subprocess with a 32 MiB input ceiling, a 1,000,000-byte
  extracted text ceiling, a 768 MiB address-space limit, and the configured
  parser timeout per file. PDF pages and workbook cells and ZIP expansion
  are bounded. PDF extraction uses an existing text layer. Workbook readers
  consume cached cell values without evaluating formulas or loading macros.
- The scanner uses deterministic, versioned potential-match rules for the
  initial data categories. This slice uses pattern and context rules instead
  of adding Presidio or a statistical name recognizer as a dependency.
  Confidence values reflect rule strength. Findings include a location in
  extracted text and a fixed redaction marker. The HMAC key stays in
  configuration, with the category and canonical value domain-separated and
  the key version stored beside each digest.
- Migration `0004_scan_findings` adds scan jobs, file metadata, fingerprints,
  and findings. File results and their counters are committed together;
  malformed and encrypted documents receive fixed reason codes.
- All 28 backend tests passed on WSL with disposable PostgreSQL and Redis.
  The upgrade from `0003_scan_sources` to `0004_scan_findings` passed with
  no schema drift. Tests covered all seven reader formats, limits, unsafe
  links, masking, per-file error isolation, and versioned correlation.

## Background processing

- Migration `0005_scan_queue` adds durable lease, cancellation, and retry
  state. Redis sends fixed wake-up notifications. The worker also polls
  PostgreSQL so a missed notification cannot strand a queued scan.
- An operator can start, poll, and cancel a scan by ID through the API.
  The worker snapshots discovered file metadata and commits results alongside
  progress. A replacement worker resumes pending files. Stale workers cannot
  commit after a replacement acquires the job, and jobs fail after three
  worker attempts.
- Verified 32 backend tests on WSL with disposable PostgreSQL and Redis,
  including a worker subprocess, missing Redis notification recovery, stale
  worker fencing, cooperative cancellation, and retry exhaustion. Migration
  from `0004_scan_findings` had no schema drift.

## Browser scan workflow

- Admin and analyst sessions can manage sources, confirm scan starts, see
  live file and finding counts, and request cancellation. Scan History shows
  the latest 50 jobs and refreshes from the persisted API.
- ESLint, Prettier, TypeScript, and the Vite build passed. Five Chromium tests
  passed against the live API and worker with synthetic data, including adding,
  disabling, enabling, and renaming a source and verifying real result counts.

## Findings inventory and review

- Admins and analysts can filter by category, source, file type, confidence,
  review status, UTC scan dates, and scan ID. Search terms are sent in the
  request body. Findings return masked evidence and relative metadata, with
  detector-based redaction applied to displayed paths and source names.
- Migration `0006_finding_review` defaults findings to needs review. Review
  changes store the actor and timestamp with an audit event. The workflow
  uses structured review states and omits free-text review notes.
- Related occurrences are shown in a paginated table from the selected
  finding. The API keeps fingerprint digests, keys, and absolute paths private.
- Verified 33 backend tests and five Chromium tests across the live API,
  PostgreSQL, Redis, and worker. The migration from `0005_scan_queue` applied
  cleanly, and Alembic detected no schema drift.

## Operational overview

- Overview displays persisted source and scan totals, processed file counts,
  findings awaiting review, recent scans, and findings by category. Links
  open the applicable filtered Discoveries views.
- Backend checks verified that reviewing a finding updates the awaiting
  review count. Chromium verified that a completed scan appears in Overview
  and that its review link opens the filtered inventory.

## Masked reports

- Administrators and analysts can download filtered CSV and JSON reports.
  A report includes generation time, scope, filters, scan references, and
  allowlisted finding fields. Findings are identified by UUID and evidence
  is redacted. Reports are capped at 10,000 rows and downloads are audited.
- CSV includes one report metadata record and one record per finding.
  JSON includes the same structured data in an envelope. File paths,
  source labels, raw identifiers, and fingerprint digests are excluded.
- The live browser suite covered downloading and inspecting both formats
  after a synthetic scan and review. Backend tests covered empty reports,
  limits, audit records, origin checks, and private field exclusion.

## Synthetic acceptance demo

- `scripts/seed_demo.py` creates labelled TXT, CSV, JSON, PDF, and XLSX files
  with synthetic duplicate values and a deliberate false positive. It also
  creates unsupported, oversized, malformed, and permission fixtures.
- The acceptance test used a real worker and disposable PostgreSQL and Redis.
  It verified file outcomes, read-only behavior, filtering, correlation,
  audited review, both export formats, and persistence across API lifecycles.
  See [the demo guide](../docs/DEMO.md) for the browser workflow.

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

- Account provisioning and administrator password recovery are local. The WSL startup script prompts for the first administrator when needed. The default development browser origin uses loopback HTTP.
- Start with `bash start.sh` on WSL to apply pending migrations automatically, or run `alembic upgrade head` during manual setup. Migration verification used disposable databases.
- Browser scan launch, history, reviews, and related occurrences are available. The synthetic acceptance workflow is available on WSL/Linux. Native Windows worker execution remains pending.
