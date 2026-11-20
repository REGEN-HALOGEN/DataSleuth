# DataSleuth

## Product summary

**DataSleuth** is a privacy-aware personal-data discovery and exposure-mapping platform for organisations. It helps authorised teams understand what personal data exists in approved data sources, where that data is stored, how copies relate to one another, and which findings may require review.

The product is designed as a practical privacy-engineering tool with a DPDP-oriented data inventory workflow. It is not a legal-compliance certification product, a DLP replacement, or an automated legal decision-maker.

## Problem

Organisations commonly have personal information spread across spreadsheets, PDFs, exported reports, shared folders, and databases. Teams may not have a reliable inventory of those locations. Copies can remain in unexpected folders long after the original business process has ended. Manual audits are slow, inconsistent, and difficult to repeat.

DataSleuth reduces the manual effort of discovering and inventorying personal data. It scans only sources explicitly configured by an authorised operator, identifies likely personal-data elements, records source and file metadata, and presents reviewable findings with traceable evidence.

## Target users

- **Privacy / data-protection teams:** build and maintain a data inventory, review data categories, and identify records requiring governance follow-up.
- **Security teams:** locate potentially exposed personal information in authorised storage locations and prioritise investigation.
- **IT / system administrators:** understand which approved folders and systems are being scanned and maintain source configurations.
- **Consultants / auditors:** produce an evidence-backed discovery report from a controlled assessment.

## Product goals

1. Discover likely personal data in approved local folders and supported documents.
2. Classify findings by data category, confidence, and source context.
3. Preserve useful evidence without unnecessarily retaining raw personal information.
4. Correlate matching or likely related values across scanned files using keyed fingerprints.
5. Give users a useful inventory with filters, source detail, review status, and export capability.
6. Provide an explainable, DPDP-oriented governance view that distinguishes technical observations from legal conclusions.
7. Make the product credible in a live demonstration using synthetic data.

## Non-goals

- Scanning networks, endpoints, cloud tenants, or third-party accounts without explicit integrations and authorisation.
- Automatically accessing personal mailboxes, messaging accounts, or external services.
- Automatically deleting, modifying, or moving source files.
- Declaring that an organisation is legally compliant or non-compliant.
- Treating a regular-expression match as proof that an identifier is genuine.
- Storing or displaying full Aadhaar, PAN, account, or other sensitive values by default.
- Building a general-purpose SIEM, antivirus, vulnerability scanner, or full DLP platform.

## Main workflows

### 1. Create a scan source

An authenticated operator adds an approved local directory, gives it a clear name, reviews the configured path, and starts a scan. The interface must explain that scanning is read-only and restricted to the configured path.

### 2. Run and monitor a scan

The operator sees queued, running, completed, completed-with-errors, or failed states; progress counts; elapsed time; and concise error details. A scan can be cancelled safely. Scanning must not execute files or macros.

### 3. Review discoveries

The operator opens the discovery inventory, filters by category, confidence, source, file type, scan date, or review status, and inspects a finding. Evidence should be redacted or masked. The interface should show why a detector matched and how confident the result is.

### 4. Understand related copies

Where the same normalised value is detected in multiple files, the platform uses a keyed HMAC fingerprint to correlate occurrences without using the raw value as the correlation key. The UI presents a relationship between occurrences and their source files. It must not imply that two records belong to the same person merely because one field matches.

### 5. Review exposure indicators

The platform highlights technical indicators such as broad filesystem permissions where they can be safely and reliably inspected on the host OS. These indicators are leads for human review, not proof of external exposure or a breach.

### 6. Export an inventory

An authorised user exports a CSV or JSON report containing approved metadata, classifications, source references, confidence, review status, and masked evidence. Raw personal values are excluded by default.

## Core product principles

- **Privacy by design:** minimise collection, mask findings, restrict access, and keep scan operations read-only.
- **Explainability:** every finding should show its source, detector, confidence, and supporting redacted context.
- **Human review:** uncertain detections and risk indicators require a person to confirm or dismiss them.
- **Least privilege:** scan only explicitly approved locations and never elevate privileges automatically.
- **Honest status:** show real scan progress and actual results; never fabricate metrics or claim a scan is live when it is not.
- **Demo safety:** use clearly labelled synthetic data for demonstrations and screenshots.

## Success criteria for the first release

- A user can create, run, monitor, cancel, and inspect a scan of an approved local directory.
- Supported file types are parsed without executing embedded content.
- The system detects the initial set of PII patterns and presents confidence and masked evidence.
- Duplicate-value correlation works through keyed fingerprints, with no raw PII in normal application logs.
- Users can search, filter, review, and export discoveries.
- The UI has no dead controls, misleading placeholder charts, or fabricated scan results.
- Automated tests cover detection, masking, fingerprinting, path restrictions, and core API workflows.
- The application can be started locally on Windows using documented commands and a reproducible development setup.
