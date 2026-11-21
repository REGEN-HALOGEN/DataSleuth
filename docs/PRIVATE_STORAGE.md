# Private document sources

DataSleuth supports two source types. A directory source grants read-only access
to approved paths on the worker host. A private document source holds one
immutable upload owned by one organisation. Both use the same scan queue,
isolated parser, detection, review and export code.

## Configuration

Apply `0008_private_documents` and upgrade the API and worker together before
enabling uploads. Existing directory sources require no changes. Run both
processes on WSL/Linux for private documents. A filesystem-only installation
can leave the four storage settings blank.

| Server setting | Purpose |
| --- | --- |
| `SUPABASE_STORAGE_URL` | Trusted Storage API base, `https://PROJECT_REF.supabase.co/storage/v1`. Disposable local Storage may use `http://127.0.0.1:PORT` with an optional `/storage/v1` path. |
| `SUPABASE_STORAGE_BUCKET` | Existing private bucket. Use a short lowercase alphanumeric or hyphenated bucket ID starting with a letter or digit. |
| `SUPABASE_STORAGE_KEY` | Server secret for bucket inspection and object creation, authenticated retrieval and deletion. The transport supports Supabase secret-key headers and legacy server JWTs. |
| `UPLOAD_INTEGRITY_KEY` | Independent random secret of at least 32 characters, shared by the API and worker. Protect and back it up. Rotation changes verification of existing uploads. |
| `UPLOAD_RETENTION_HOURS` | Raw-document lifetime after successful upload, default 24 hours. |
| `UPLOAD_ORG_QUOTA_BYTES` | Maximum reserved and retained raw bytes per organisation, default 128 MiB. Up to 1,024 outstanding documents per organisation. |

Use a dedicated project/bucket and restrict object access to the trusted
server. A private bucket can still grant access through permissive Storage RLS
policies. Verify anonymous and ordinary user credentials cannot read, list,
write, overwrite or delete its contents. Supabase server secret keys can bypass
RLS. Control access to those credentials, bucket configuration, provider logs
and backups at the provider. Store the credentials only on the API and worker.
[Supabase bucket access model](https://supabase.com/docs/guides/storage/buckets/fundamentals)
and [server key permissions](https://supabase.com/docs/guides/getting-started/api-keys).

Configure identical settings on API and worker. A worker claims private jobs
for its configured provider URL and bucket. Local jobs still require the
worker's organisation root assignment. Drain outstanding jobs and confirm
deletion of retained objects before changing bucket location, removing
credentials or rotating the integrity key. Provider credentials can be rotated
independently while retaining access to the same bucket.

## Operator workflow

In **Scan Sources**, use **Upload a private document**, give it a non-sensitive
label, and choose one supported file. The browser transmits its extension,
size and bytes. Object keys contain only the organisation and source UUIDs.
The worker displays a generic file label such as `document.pdf`. Once the
source is enabled, use the existing read-only scan confirmation.

The API requires an operator session and the exact browser origin for mutations.

| Operation | Behaviour |
| --- | --- |
| `GET /api/v1/documents/capabilities` | Reports whether uploads are configured, the byte limit, and supported extensions with MIME types. |
| `POST /api/v1/documents` | Reserves quota for a JSON body containing `name`, `extension` (including the dot), and positive integer `size_bytes`. Returns a disabled pending source. |
| `PUT /api/v1/documents/{id}/content` | Streams raw bytes with the expected Content-Type. A successful upload marks the source ready. A ready source refuses replacement. |
| `DELETE /api/v1/documents/{id}` | Requests physical deletion and immediately disables the source. An active scan returns 409. Poll the existing source detail endpoint for the final state. |
| `GET /api/v1/sources/{id}` | Includes `upload_state`, `extension`, `size_bytes`, and `expires_at`. Uploaded sources return a null `configured_path`. Directory registration retains its existing payload. |

Uploads are bounded by the configured file limit and the 32 MiB reader ceiling.
The API validates the actual byte count and declared media type. A bounded
subprocess checks UTF-8 text, JSON syntax, a PDF signature, or the workbook
content-type manifest. Full parsing and detection occur in the worker. Two
uploads can be in progress per API process. Private temporary files close on
success, error or cancellation.

The server checks bucket privacy before writing and reading. It sends no
download URL to the browser and accepts no caller-supplied provider endpoint
or object key. The worker streams authenticated bytes to private temporary
storage and verifies the exact size and organisation- and source-bound HMAC
before handing a descriptor to the parser. A provider outage leaves durable
work for the existing fenced retry path. A content mismatch fails that file.

## Retention and failure recovery

Reservations expire after 15 minutes. Expired ready documents reject new scans.
The worker periodically deletes due objects after active scans finish, including
abandoned reservations and ambiguous uploads. A provider write with an unknown
outcome is quarantined for cleanup. Register a new source to retry that upload.
A failed provider deletion remains pending for retry. Check the source state
after requesting deletion. Physical deletion requires a running worker with
the matching bucket configuration and functioning credentials.

A completed purge retains a disabled source and historical masked findings,
reviews, reports' underlying metadata and audit records. Disabling a directory
source never removes its files. Configure provider backup retention separately.
Provider administrators can change bucket visibility or permissions after an
application check. Verify those settings in staging before admitting real
documents.

## Verification

The storage regression suite requires the normal disposable PostgreSQL/Redis
test settings and a dedicated loopback Supabase Storage service with a private
bucket. Set the three `DATASLEUTH_TEST_SUPABASE_STORAGE_*` settings ending in
`URL`, `BUCKET`, and `KEY`. The fixture supplies a synthetic integrity key.
Run `python -m pytest tests/test_private_documents.py` from `backend`. Without
those settings the real-provider tests skip. To include uploads in the live
browser suite, configure both running services and set
`DATASLEUTH_E2E_UPLOAD=1` alongside the existing E2E settings.

The implementation was exercised against a disposable self-hosted Supabase
Storage REST service using a test service-role JWT. Hosted gateway, modern
secret-key authentication, provider policy and backup behaviour require
separate staging verification.
