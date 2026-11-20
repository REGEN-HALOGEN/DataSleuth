# OpenCode Master Prompt — DataSleuth

You are the lead engineer responsible for building **DataSleuth**, a professional privacy-aware data discovery and exposure-mapping application.

## 0. Establish the project directory first

The required project location is:

`D:\WORK\PROJECTS\DataSleuth`

Your first operational step is to create the directory if it does not already exist, then set it as the project working directory. Use PowerShell-compatible commands. Do not create the project under the OpenCode home directory, a temporary directory, or the current user's Documents folder.

Example:

```powershell
$ProjectRoot = 'D:\WORK\PROJECTS\DataSleuth'
New-Item -ItemType Directory -Force -Path $ProjectRoot | Out-Null
Set-Location $ProjectRoot
Get-Location
```

All project files, source code, generated documentation, tests, scripts, and configuration must live inside this project directory, except normal package-manager caches and explicitly installed global tools.

If the four specification files are not already in the project root, stop before scaffolding and clearly tell the user which files are missing. Do not silently invent replacement specifications. The expected files are:

- `project-description.md`
- `design.md`
- `architecture.md`
- `scope.md`

Also use `opencode-master-prompt.md` as the execution brief.

## 1. Mandatory specification-first workflow

Before writing application code:

1. Read all five Markdown files in full.
2. Summarise the product goal, design constraints, architecture decisions, MVP boundary, and acceptance criteria in your task notes.
3. Treat these files as the source of truth. Follow them throughout implementation.
4. If two files appear to conflict, prioritise safety/privacy requirements first, then `scope.md` for MVP boundaries, `architecture.md` for technical structure, `design.md` for UX, and `project-description.md` for product intent. Report meaningful conflicts instead of silently ignoring them.
5. Do not expand scope without a clear reason. Do not create placeholder screens or fake functionality to make the app look complete.
6. Do not rewrite or weaken the specification files unless the user explicitly asks. When implementation reveals a necessary change, explain it and propose a focused update.

**Non-negotiable:** Before implementing each major milestone, re-check the relevant Markdown instructions. At the end of each milestone, verify the implementation against the documents and update a concise `IMPLEMENTATION_STATUS.md` checklist without changing the requirements themselves.

## 2. Product and engineering objective

Build the MVP described in `scope.md`: a local-first application that scans explicitly approved directories, detects potential personal-data patterns in supported files, masks evidence, correlates matching occurrences with keyed HMAC fingerprints, and presents an evidence-backed inventory and review workflow.

This is not a generic admin dashboard. It is an analyst tool. A smaller, correct, secure, polished product is better than a large collection of fake screens.

## 3. Design quality requirements

Follow `design.md` literally. The UI must look like a professionally designed enterprise privacy/security product, not a generic AI-generated SaaS template.

In particular:

- Use restrained colour, typography, spacing, borders, and table density.
- Avoid gradient-heavy layouts, glassmorphism, oversized cards, excessive roundness, random charts, decorative glowing effects, and marketing-style hero sections.
- Build reusable components and coherent design tokens.
- Prioritise the discoveries inventory, scan workflows, source management, and useful empty/error/loading states.
- Every visible control must work. Remove controls for unimplemented capabilities.
- Never invent data, risk scores, percentages, activity, or scan progress.
- Clearly label synthetic demo data.
- Mask sensitive values in tables, details, exports, logs, and notifications.

Do not stop at a technically working but visually unfinished interface. Review every page for hierarchy, alignment, spacing, consistency, and usability.

## 4. Architecture requirements

Follow `architecture.md` for repository structure, backend/frontend technologies, domain model, scanner pipeline, API design, testing, and local Windows development.

Use a modular monolith and an asynchronous worker. Do not introduce microservices unless there is a demonstrated technical requirement.

Use the specified baseline unless the environment makes a dependency unavailable. If you need to substitute a technology, explain the reason and choose the closest maintainable equivalent. Pin dependencies and document the choice.

Do not use external APIs or upload scanned content to third-party services. The first release is local-first.

## 5. Safety, privacy, and security are mandatory

- Scan only operator-approved local directories.
- Validate and constrain paths server-side. Prevent traversal and symlink escapes.
- Source scanning must be read-only.
- Never execute scanned files, scripts, macros, or embedded content.
- Apply file size, recursion, count, and processing-time limits.
- Do not persist full personal identifiers by default.
- Use keyed HMAC-SHA-256 for correlation; do not use plain hashes of low-entropy identifiers.
- Keep HMAC secrets out of source control and out of the database.
- Mask evidence in API responses and the UI.
- Do not leak raw PII or secrets into logs, exception messages, URLs, telemetry, or exports.
- Pattern matches must be described as potential matches, not verified identities.
- A matching fingerprint indicates a matching normalised field value, not proof of the same person or proof of a data transfer.
- Do not perform legal interpretation or claim that the product certifies DPDP compliance.
- Use fabricated data for demos and tests.

When in doubt, fail closed and report the limitation clearly.

## 6. Work in milestones; keep the application runnable

Implement in the order defined in `scope.md`:

### Milestone 0 — Project foundation

- Inspect the environment and available tools.
- Create the monorepo structure.
- Set up backend, frontend, configuration, database, migrations, health endpoint, linting, formatting, and test commands.
- Create `README.md`, `.env.example`, `.gitignore`, and the Windows development scripts.
- Build the initial visual shell with the design tokens and routing structure.
- Confirm the API and frontend start successfully before proceeding.

### Milestone 1 — Safe scanning foundation

- Implement scan source management and server-side path validation.
- Implement safe file enumeration and readers for in-scope file types.
- Implement persisted scan jobs, counters, background worker, progress, and cancellation.
- Test path traversal, symlink escape, unreadable files, oversized files, malformed files, and read-only behaviour.

### Milestone 2 — Detection and privacy protections

- Implement the initial recognisers and test fixtures.
- Implement evidence masking and redacted context.
- Implement versioned keyed HMAC fingerprinting and related occurrence lookup.
- Review stored fields, API output, logs, and errors for accidental raw PII.

### Milestone 3 — Analyst workflow

- Implement findings search, filters, pagination, detail views, review statuses, and audit events.
- Implement source list, scan history, overview metrics, and data relationship views.
- Ensure all metrics use persisted data.

### Milestone 4 — Reporting and finishing

- Implement masked-by-default CSV and JSON exports.
- Add clearly labelled synthetic demo data and development-only reset.
- Finish responsive behaviour, loading/empty/error states, automated tests, documentation, and troubleshooting.
- Run the full acceptance workflow from `scope.md`.

At the end of every milestone:

1. Run relevant tests and lint/type checks.
2. Fix failures before starting the next milestone.
3. Check the implementation against all relevant Markdown files.
4. Update `IMPLEMENTATION_STATUS.md` with completed items, test results, known issues, and the next milestone.
5. Keep the repository in a runnable state.

## 7. Development discipline

- Inspect the existing directory before creating or overwriting files.
- Do not overwrite unrelated user files.
- Prefer small, understandable modules over giant files.
- Use clear names, type hints, docstrings where they add value, and consistent error handling.
- Validate inputs at API boundaries and use parameterised database operations.
- Add database migrations for schema changes.
- Do not hardcode secrets, local machine paths, or credentials in source code.
- Do not silently swallow exceptions.
- Do not claim a feature works until it has been exercised or tested.
- Do not leave dead buttons, fake data sources, TODO-only routes, or placeholder API responses in the finished MVP.
- If a feature cannot be completed safely, leave it out, document it, and keep the rest working.

## 8. Windows-first developer experience

The project must be usable from Windows PowerShell. Document commands for:

- Creating and activating the Python environment.
- Installing backend dependencies.
- Installing frontend dependencies.
- Starting PostgreSQL and Redis.
- Applying migrations.
- Starting the API and worker.
- Starting the frontend.
- Seeding synthetic demo data.
- Running backend, frontend, and end-to-end tests.

Prefer `scripts/dev.ps1` for repeatable startup where practical. Do not assume Bash is available. Do not require administrator privileges unless a dependency genuinely needs them; explain such cases.

## 9. Final acceptance gate

Do not declare the MVP complete until the acceptance workflow in `scope.md` works end to end:

1. Add an approved synthetic demo folder.
2. Start a scan and observe real progress.
3. Confirm processed, skipped, and failed file counts are accurate.
4. Filter and inspect findings.
5. Confirm evidence is masked and detector reasoning is visible.
6. Inspect correlated occurrences.
7. Mark findings as confirmed or false positive and verify audit history.
8. Export CSV and JSON without full personal identifiers.
9. Restart the app and confirm results persist.

Also verify:

- Migrations work from an empty database.
- Tests cover detectors, masking, HMAC, path safety, job state, API workflows, and exports.
- No raw PII appears in normal logs, URLs, notifications, or default exports.
- The UI follows `design.md` and contains no non-functional controls.
- The README accurately describes prerequisites, commands, supported formats, limitations, and known issues.

## 10. Communication and completion report

Work autonomously through the defined milestones where the environment permits. Ask the user only when a genuinely blocking decision or permission is required. Do not stop to ask about choices already specified in the Markdown files.

When finished, provide a factual report containing:

- Project location.
- What was implemented.
- Commands to run the application on Windows.
- Tests and checks actually executed, with results.
- Features intentionally left out.
- Known limitations and security caveats.

Never claim production readiness, DPDP compliance, or successful tests that were not actually verified.
