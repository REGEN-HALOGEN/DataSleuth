# DataSleuth Technical Architecture

## 1. Architecture decision

Build DataSleuth as a **modular monolith with an asynchronous scan worker**. This is simpler to develop, test, and deploy than premature microservices, while keeping domain boundaries clear enough to split later if justified.

The first release is a local-first development application for Windows. The backend scans only explicitly configured local directories. Database connectors, cloud storage integrations, endpoint agents, multi-tenant SaaS hosting, and automatic remediation are future extensions, not MVP requirements.

## 2. Technology baseline

Use supported stable versions available in the development environment. Pin dependencies in lockfiles or requirements files. Do not silently use experimental releases.

### Frontend

- React with TypeScript.
- Vite for the frontend development/build pipeline.
- Tailwind CSS for layout and tokens, with a small reusable component system.
- React Router for navigation.
- TanStack Query for server state and request caching.
- React Hook Form and Zod for forms and client-side validation.
- A graph library such as React Flow for the relationship view.
- A chart library only for real, useful aggregate data.

### Backend

- Python with FastAPI.
- Pydantic schemas for request/response validation.
- SQLAlchemy 2.x for persistence.
- Alembic for database migrations.
- PostgreSQL as the primary database.
- Redis and Celery (or a similarly simple queue/worker arrangement) for background scan jobs.
- Structured application logging with sensitive-field redaction.

### Detection and parsing

- Microsoft Presidio as a starting point for recognisers and analysis orchestration.
- Custom recognisers for India-relevant patterns such as PAN and Aadhaar-shaped values, with clear caveats.
- PyMuPDF for PDF text extraction.
- openpyxl for Excel workbooks.
- Python standard CSV and text parsing where appropriate.
- Optional OCR for image-only PDFs is out of MVP unless implemented with strict resource limits and a clear dependency check. Do not make OCR a blocker for the first working release.

### Development and operations

- Docker Compose for PostgreSQL and Redis where Docker is available; Podman compatibility is desirable.
- `.env.example` for local configuration, never commit real secrets.
- Pytest for backend tests.
- Vitest and React Testing Library for frontend tests.
- Playwright for a small number of end-to-end critical workflows if feasible.
- Ruff and a Python type checker; ESLint and Prettier for frontend quality.

## 3. High-level component model

```text
Browser (React + TypeScript)
        |
        | HTTPS / JSON API
        v
FastAPI application
  |        |          |
  |        |          +---- Reporting / export module
  |        +--------------- Inventory / review module
  +------------------------ Source and scan orchestration
        |
        +---- PostgreSQL
        |
        +---- Redis queue
                 |
                 v
            Scan worker
                 |
                 +---- Approved local directory only
                 +---- Safe file readers
                 +---- Text extraction
                 +---- PII recognisers
                 +---- Masking and HMAC fingerprinting
                 +---- Persist metadata and findings
```

The worker must not execute scanned files, macros, scripts, or embedded content. It must read only paths approved by the operator and enforce the same path restrictions as the API.

## 4. Suggested repository structure

```text
DataSleuth/
├── project-description.md
├── design.md
├── architecture.md
├── scope.md
├── opencode-master-prompt.md
├── README.md
├── .env.example
├── .gitignore
├── compose.yaml
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── scanners/
│   │   ├── detectors/
│   │   ├── workers/
│   │   └── reports/
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   ├── hooks/
│   │   ├── lib/
│   │   ├── routes/
│   │   ├── styles/
│   │   └── types/
│   └── tests/
├── scripts/
│   ├── dev.ps1
│   └── seed_demo.py
└── docs/
    ├── api.md
    └── security-model.md
```

Adjust only when a concrete implementation reason exists. Keep the docs at the project root.

## 5. Core domain model

Use UUID primary keys and UTC timestamps. Store paths carefully; avoid exposing absolute paths to unauthorised users or in public URLs.

### ScanSource

- `id`
- `name`
- `source_type` (MVP: `local_directory`)
- `configured_path` (protected at rest where practical; never place in client-side URL)
- `enabled`
- `created_at`, `updated_at`
- `last_scan_at`

### ScanJob

- `id`
- `source_id`
- `status` (`queued`, `running`, `completed`, `completed_with_errors`, `failed`, `cancelled`)
- `started_at`, `finished_at`
- `files_discovered`, `files_processed`, `files_skipped`, `files_failed`
- `findings_created`
- `error_summary` (sanitised; no raw file contents or identifiers)
- `created_by` (nullable until real authentication is implemented)

### ScannedFile

- `id`
- `scan_job_id`, `source_id`
- `relative_path`
- `file_name`
- `file_extension`
- `file_size_bytes`
- `modified_at` if available
- `content_sha256` for file-change detection, not for storing source content
- `parse_status`
- `first_scanned_at`, `last_scanned_at`

Avoid storing full file contents. Consider path normalisation and case sensitivity differences across Windows filesystems.

### Finding

- `id`
- `scanned_file_id`
- `category` (for example, email, phone, PAN-shaped, Aadhaar-shaped, name, bank-related)
- `detector_id` and `detector_version`
- `confidence` (normalised 0–1)
- `masked_evidence`
- `evidence_context` (short, redacted context only)
- `fingerprint_id` (nullable)
- `review_status` (`needs_review`, `confirmed`, `false_positive`, `follow_up`)
- `review_note` (must not contain raw PII)
- `reviewed_by`, `reviewed_at`
- `created_at`

### DataFingerprint

- `id`
- `category`
- `key_version`
- `digest`
- `created_at`

Create fingerprints with a keyed HMAC over a documented canonical representation: `HMAC-SHA-256(secret_key, category || separator || normalized_value)`. Use separate domains/categories to prevent cross-category collisions. Store the secret outside the database, in environment configuration for local development or a proper secret manager in production. Never use a plain SHA hash of low-entropy personal identifiers as a privacy-preserving substitute.

Key rotation needs a documented strategy. For the MVP, version the key and avoid silently mixing fingerprints generated under different keys. A matching digest only means the same canonical value was observed; it does not prove two records refer to the same person.

### AuditEvent

- `id`
- `actor_id` (nullable for local development)
- `action`
- `entity_type`, `entity_id`
- `metadata` (allowlisted fields only; no raw PII or secrets)
- `created_at`

## 6. Scanner and detector pipeline

1. Validate that the configured path exists, is a directory, and is within the explicitly approved scan root.
2. Resolve and normalise paths. Reject path traversal and handle symlinks conservatively; do not follow symlinks outside the approved root.
3. Enumerate supported files with configurable size, depth, and count limits.
4. Skip encrypted, unsupported, oversized, temporary, or unreadable files with a reason code.
5. Parse content using format-specific safe readers. Never execute macros, scripts, or embedded objects.
6. Send extracted text to recognisers. Store detector ID, category, confidence, and redacted evidence.
7. Normalise a candidate only in memory, calculate the keyed fingerprint, then discard the raw candidate unless a narrowly justified feature requires temporary processing. Do not persist raw candidate values by default.
8. Persist file metadata, masked finding, fingerprint reference, and scan counters.
9. Emit progress updates and sanitised logs.

### Detection caveats

- Pattern matching is not identity verification. A regex match for PAN or an Aadhaar-shaped sequence is only a potential match.
- Use checksums or format validation only where a documented validation method exists and is legally appropriate.
- Confidence values must be based on recogniser behaviour and context, not invented to make a dashboard appear sophisticated.
- Names are difficult to classify reliably without context. Keep name detection conservative and explain its limitations.
- Keep detector definitions versioned and covered by positive and negative test fixtures.

## 7. Security and privacy requirements

These are architecture requirements, not optional polish.

- Read-only source scanning. No source file writes, renames, moves, or deletes.
- Explicit source registration and operator confirmation before each scan.
- No network scanning and no implicit cloud access.
- No raw PII in application logs, exception traces, analytics events, URLs, or toast notifications.
- Mask findings in the API and UI by default.
- Do not store raw personal values by default. If a future feature proposes doing so, it requires a documented threat model and explicit approval.
- Keep HMAC keys out of source control and the database.
- Use parameterised database operations and validate all API inputs.
- Apply file size, page count, recursion depth, and processing-time limits.
- Handle malformed files safely and isolate parser failures per file.
- Use authentication and role-based authorisation before exposing the product beyond a single trusted local developer. Do not claim production readiness without implementing these controls.
- Protect exports and avoid predictable public report URLs.
- Use CSRF protection where cookie-based authentication is used; configure CORS narrowly.
- Maintain an audit trail for source changes, scan starts/cancellations, review actions, and exports.
- Keep dependencies patched and run dependency/security checks before release.

## 8. API surface (initial proposal)

Use `/api/v1` and consistent response/error schemas.

- `GET /health` — process health, without secrets.
- `GET /api/v1/overview` — real aggregate metrics and recent scans.
- `GET /api/v1/sources` — list sources.
- `POST /api/v1/sources` — create an approved local-directory source.
- `GET /api/v1/sources/{id}` — source detail.
- `PATCH /api/v1/sources/{id}` — update safe source metadata or enabled state.
- `POST /api/v1/scans` — queue a scan for an enabled source.
- `GET /api/v1/scans` — list scans.
- `GET /api/v1/scans/{id}` — scan status and counters.
- `POST /api/v1/scans/{id}/cancel` — request safe cancellation.
- `GET /api/v1/findings` — paginated/filterable findings.
- `GET /api/v1/findings/{id}` — finding detail with masked evidence.
- `PATCH /api/v1/findings/{id}/review` — update review status and note.
- `GET /api/v1/fingerprints/{id}/occurrences` — related occurrences, without revealing raw values.
- `GET /api/v1/reports/findings.csv` — filtered metadata export.
- `GET /api/v1/reports/findings.json` — filtered metadata export.

Validate source IDs, filters, page size, sort fields, and export scope. Do not allow arbitrary filesystem paths in scan-start requests; scans should reference a previously approved source ID.

## 9. Background jobs and progress

The API creates scan jobs and queues them. The worker owns the scan lifecycle and updates persisted counters/status. The frontend polls scan details initially; server-sent events can be considered later if polling proves insufficient.

Cancellation must be cooperative and checked between files and parsing stages. A cancelled job must not be reported as completed.

## 10. Configuration and secrets

Document environment variables in `.env.example`, including database URL, Redis URL, application secret, HMAC key, HMAC key version, allowed scan roots, file size limit, recursion depth, and log level.

- Use development-only values in `.env.example`.
- Fail clearly when required secrets are absent; do not silently generate a production key on every restart.
- Never commit `.env` or real keys.
- Restrict configurable scan roots; do not treat an arbitrary request path as authorised.

## 11. Testing strategy

Backend tests must include:

- Positive and negative fixtures for each recogniser.
- Masking tests proving complete identifiers are not returned.
- HMAC tests proving same normalised value and key produce the same digest, and different keys produce different digests.
- Tests showing raw PII is absent from logs and error summaries.
- Path traversal, symlink escape, oversized file, malformed file, and unsupported extension tests.
- Read-only behaviour tests where practical.
- Scan state transitions and cancellation tests.
- API pagination, filtering, review, and export tests.

Frontend tests must cover core form validation, empty/loading/error states, table filtering, and review interactions. Add an end-to-end test for add source → run scan → inspect finding → mark review status → export.

## 12. Local development and Windows support

Provide clear PowerShell commands and scripts. Do not assume Bash-only tooling.

The README must explain prerequisites, environment setup, database startup, migrations, backend startup, worker startup, frontend startup, demo-data seeding, tests, and troubleshooting. Prefer repeatable commands and avoid requiring administrator privileges.

## 13. Architecture evolution

Only after the MVP is stable, consider:

- Read-only database connectors.
- Cloud storage integrations with explicit credentials and scopes.
- Windows ACL inspection improvements.
- OCR for image-only documents.
- Multi-user authentication and RBAC.
- Multi-tenant hosting with tenant isolation.
- Consent-management integrations and request workflows.

Do not implement these future directions as fake screens or placeholder buttons in the MVP.
