# DataSleuth Scope and Delivery Plan

## 1. Delivery objective

Deliver a working, demonstrable MVP of DataSleuth: a local-first application that scans operator-approved directories, discovers potential personal-data patterns in supported files, masks evidence, correlates occurrences with keyed fingerprints, and presents an evidence-backed inventory.

The first release should prioritise correctness, safe handling, explainability, and a polished analyst workflow over a large feature count.

## 2. MVP scope (must deliver)

### A. Project foundation

- Monorepo with `backend/` and `frontend/`.
- Local development configuration and `.env.example`.
- PostgreSQL migrations and reproducible setup scripts.
- Health endpoint and structured, redacted logging.
- README with Windows PowerShell instructions.

### B. Source management

- Add, list, enable/disable, and inspect local-directory scan sources.
- Validate paths server-side and constrain scanning to configured approved roots.
- Do not expose arbitrary-path scanning through the scan API.
- Clearly explain read-only operation and supported file types.

### C. Scanning

- Asynchronous scan jobs with persisted status and counters.
- Supported formats: `.txt`, `.csv`, `.log`, `.json`, `.pdf` with extractable text, `.xlsx`, and `.xlsm` parsed without executing macros. For `.xlsm`, read cell values only; never execute VBA.
- Explicit file-size, recursion-depth, file-count, and processing-time limits.
- Safe handling of unreadable, encrypted, malformed, unsupported, and oversized files.
- Cooperative cancellation.
- File metadata inventory; do not persist full source contents.

### D. Detection

Initial detectors:

- Email address.
- Phone number with configurable country context; India should be the default demo context.
- PAN-shaped value.
- Aadhaar-shaped 12-digit value with conservative context checks.
- Bank-account-like number and IFSC-shaped value where feasible.
- Conservative name/entity recogniser only if the selected recogniser provides explainable results.

Requirements:

- Every detector has an ID, category, version, tests, and confidence output.
- Label results as potential matches, not verified identities.
- Store masked evidence and short redacted context only.
- Do not store the full candidate value by default.

### E. Fingerprint correlation

- Normalise values in memory using category-specific rules.
- Generate keyed HMAC-SHA-256 fingerprints with a versioned secret.
- Correlate occurrences with the same category and digest.
- Explain that correlation means a matching normalised field value, not proof of the same person or a data transfer.
- Never use plain SHA-256 of personal identifiers as a replacement for keyed HMAC.

### F. Findings and review workflow

- Paginated findings inventory.
- Search and filter by category, source, confidence, review status, file type, and scan.
- Detail view with source metadata, detector, confidence, masked evidence, and related occurrences.
- Review states: needs review, confirmed, false positive, follow-up.
- Record review timestamp and reviewer identity where authentication supports it; include a local-development actor marker if full authentication is deferred.
- Record audit events for review changes.

### G. Reporting

- CSV and JSON exports.
- Metadata and masked evidence only by default.
- Export scope, filters, generated time, and scan references included.
- No full personal identifiers in exports.

### H. Professional UI

Implement the product shell and these real pages:

- Overview.
- Discoveries.
- Scan Sources.
- Scan History.
- Data Relationships.
- Reports.

All visible controls must perform a real action. If any page cannot be fully delivered in the MVP, remove it from navigation rather than rendering an empty placeholder.

## 3. Explicitly out of scope for MVP

- Remote endpoint/agent deployment.
- Network discovery or port scanning.
- Microsoft 365, Google Workspace, AWS, Azure, or other cloud connectors.
- Live database connectors. Design interfaces so read-only connectors can be added later, but do not simulate them.
- Browser extensions or email integrations.
- Automatic deletion, redaction, movement, or remediation of source files.
- Consent capture, consent withdrawal propagation, or a Consent Manager product.
- Automated legal interpretation, compliance certification, or legal advice.
- Production multi-tenancy and enterprise SSO.
- OCR for scanned images unless the core MVP is already stable and there is sufficient time.
- AI/LLM-based PII detection. Prefer deterministic and explainable detectors for the first release.
- Fake breach alerts, invented risk scores, dummy activity feeds, or simulated live scanning in the real-data workflow.

## 4. Delivery milestones

### Milestone 0 — Repository and runnable skeleton

- Create backend and frontend projects.
- Establish environment configuration, database, migrations, and health endpoint.
- Establish linting, formatting, and test commands.
- Build the visual shell with route structure.

**Exit criteria:** a developer can start the API and frontend using documented Windows commands; health checks pass.

### Milestone 1 — Safe source and scanner foundation

- Implement approved source creation and validation.
- Implement safe file enumeration and supported file readers.
- Persist scan jobs, file metadata, counters, and errors.
- Add background worker and cancellation.

**Exit criteria:** a test folder can be scanned; scan states and counts are real; traversal and symlink escape tests pass.

### Milestone 2 — Detection and privacy protections

- Implement and test the initial recognisers.
- Implement evidence masking and redaction.
- Implement HMAC fingerprinting and occurrence correlation.
- Review all logs, errors, API responses, and database fields for accidental raw PII persistence.

**Exit criteria:** positive and negative fixture tests pass; the UI/API do not reveal full identifiers by default.

### Milestone 3 — Inventory and analyst workflows

- Implement findings API, filters, pagination, detail views, review states, and audit events.
- Implement overview metrics from persisted data.
- Implement source, scan history, and relationship views.

**Exit criteria:** users can complete the end-to-end analyst workflow without editing the database manually.

### Milestone 4 — Reports, polish, and demonstration

- Implement CSV/JSON exports.
- Add labelled synthetic demo dataset and development-only reset.
- Finish empty/loading/error states and responsive behaviour.
- Add end-to-end test, security checks, and documentation.

**Exit criteria:** a clean local setup supports the complete demo and the test suite passes.

## 5. Acceptance test: primary demonstration

Create a synthetic company folder containing a mix of CSV, Excel, text, JSON, and PDF files. Include deliberate duplicates, false positives, unsupported files, oversized files, and one unreadable file. Use only fabricated values; do not use real personal data.

A reviewer should be able to:

1. Add the demo folder as an approved source.
2. Start a scan and watch real progress counters update.
3. See successful, skipped, and failed files reported accurately.
4. Open the findings inventory and filter by category and confidence.
5. Inspect a finding and see masked evidence plus detector explanation.
6. Find related occurrences through fingerprint correlation.
7. Mark a finding as confirmed or false positive and see the audit history.
8. Export a CSV/JSON inventory that does not contain full identifiers.
9. Restart the application and retain scan results and review state.

## 6. Definition of done

The MVP is done only when:

- The application starts using documented Windows instructions.
- Database migrations run cleanly from an empty database.
- The backend worker processes jobs asynchronously.
- Scanning is restricted to configured directories and does not modify source files.
- Detection, masking, and HMAC correlation have automated tests.
- The UI follows `design.md` and has no non-functional controls.
- Metrics and charts use actual persisted data or are clearly labelled synthetic demo data.
- CSV/JSON exports are masked by default.
- Logs and error handling do not leak raw identifiers or secrets.
- A complete end-to-end demonstration works with synthetic data.
- Known limitations and unsupported file types are documented honestly.

## 7. Prioritisation rules

When time is limited, prioritise in this order:

1. Safe and correct scanning.
2. Reliable detection, masking, and fingerprinting.
3. Findings inventory and review workflow.
4. A polished, coherent analyst UI.
5. Reports and demo convenience.
6. Additional detectors and optional visualisations.

Do not add another feature by weakening path safety, privacy protections, test coverage, or core workflow reliability.
