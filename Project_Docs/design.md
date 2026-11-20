# DataSleuth UI / UX Design Specification

## 1. Design intent

Design DataSleuth as a serious enterprise privacy-engineering product used by security analysts, privacy teams, and IT administrators. It should feel like a mature operational tool: quiet, precise, information-dense, and trustworthy.

The interface must **not** look like a generic AI-generated SaaS template. Avoid decorative gradients, glassmorphism, oversized rounded cards, glowing borders, excessive iconography, giant empty hero sections, random charts, and arbitrary accent colours. Do not imitate a marketing landing page inside the application.

The product should look considered and editorial, with strong hierarchy, restrained colour, consistent spacing, useful tables, clear status communication, and excellent interaction details.

## 2. Visual direction

- **Overall style:** modern enterprise application; restrained, technical, calm, precise.
- **Default theme:** light theme, with a considered dark theme only if it can be implemented consistently. Do not sacrifice information hierarchy to support themes.
- **Canvas:** warm-neutral or cool-neutral light background, with white or near-white content surfaces and subtle separators.
- **Primary text:** near-black charcoal. Secondary text must remain readable, not pale grey.
- **Accent:** choose one restrained deep blue / indigo accent for primary actions and selected states. Use semantic colours only for status and risk.
- **Risk colours:** red for critical, amber for warning, blue/neutral for informational, green only for confirmed healthy/completed states. Never use colour alone to communicate meaning.
- **Borders and shadows:** prefer fine borders and subtle elevation. Avoid large shadows and glowing effects.
- **Corner radius:** restrained and consistent. Use smaller radii for controls and tables, moderate radii for panels. Avoid pill-shaped everything.

## 3. Typography

Use a professional, highly legible UI sans-serif such as Inter, Geist, or the platform system stack. Use a clear type scale rather than arbitrary sizes.

- Page titles: 24–28 px, semibold.
- Section headings: 15–18 px, semibold.
- Body and controls: 13–14 px where appropriate, with comfortable line height.
- Table content: 13–14 px; metadata may be 12 px but must remain legible.
- Numeric metrics: use tabular numerals for aligned counts and timestamps.
- Use weight and spacing for hierarchy. Do not make every label bold.

## 4. Application shell and navigation

Use a stable application shell:

- A compact left navigation rail/sidebar with product mark and product name.
- Primary navigation: **Overview**, **Discoveries**, **Scan Sources**, **Scan History**, **Data Relationships**, **Reports**.
- A restrained top bar containing current page context, global search only if genuinely functional, and the user/account menu.
- Keep the sidebar width and active state consistent across pages.
- The main content area should have a readable maximum width while allowing data tables to use available horizontal space.
- Do not add navigation items that lead to empty pages. Unimplemented future areas should not appear as working features.

## 5. Overview page

The overview is an operational summary, not a marketing dashboard.

Recommended layout:

1. Page title, one-sentence context, and a clearly placed **New scan** primary action.
2. A compact row of meaningful metrics: configured sources, files scanned, findings awaiting review, and latest scan status. Each metric must come from real backend data. If no scans exist, show a proper empty state rather than zeros presented as meaningful activity.
3. A recent scans table with source, start time, status, files processed, findings, and action.
4. A compact findings-by-category visual only when there is actual data. The chart must have labels, a useful empty state, and an accessible tabular alternative.
5. A small review queue showing the highest-priority or least-reviewed findings.

Do not use donut charts merely to fill space. Do not invent percentages, risk scores, or trends.

## 6. Discoveries inventory

This is a core working screen and should receive the most UX attention.

- Use a full-width data table with a compact toolbar.
- Provide search and useful filters: data category, confidence, source, file type, scan date, review status, and severity where supported.
- Table columns should include: category, masked detection / evidence label, source file, location, confidence, review status, and first-seen time.
- Never render the complete detected identifier in the table.
- Use predictable sorting, pagination, loading states, and query-state persistence where practical.
- Selecting a row opens a right-side detail panel or a dedicated detail view.
- Detail view shows detector name, confidence, redacted evidence, file metadata, scan reference, fingerprint correlation count, and reviewer actions.
- Review actions: mark as confirmed, mark as false positive, or mark for follow-up. Require an optional note where useful and record who changed the status and when.
- Destructive actions must be explicit and confirmed. Do not offer source-file deletion.

## 7. Scan Sources and scan workflow

### Sources page

- Show configured directories as a table or list with source name, approved path, last scan, status, and actions.
- Adding a source must use a clear, guided form. Explain path access and read-only behaviour.
- Validate paths on the backend. Prevent traversal outside approved roots and reject dangerous or inaccessible paths.
- Never silently broaden a configured scan path.

### New scan flow

Use a focused step-by-step dialog or page:

1. Select an existing source or configure a new approved directory.
2. Show what file types and detectors will be used.
3. Show exclusions and size limits.
4. Ask the operator to confirm the read-only scan.
5. Start the scan and show progress.

Progress must be based on real worker updates. Show files discovered, processed, skipped, and failed. Explain that counts can change as directory traversal proceeds.

## 8. Data Relationships page

- Use a graph only to answer a real question: which files contain correlated occurrences, or which sources are connected by matching fingerprints.
- Use a restrained graph style, clear node labels, a legend, and a details panel on selection.
- Distinguish source files, scan sources, and detected occurrences through shape or label as well as colour.
- Avoid a giant decorative network graph. Start with a selected fingerprint or finding and show only its related occurrences.
- Provide a table/list alternative for accessibility and users who prefer exact data.
- Clearly explain that a shared fingerprint indicates a matching normalised field value, not necessarily the same individual or a proven data-flow event.

## 9. Reports page

- Provide CSV and JSON exports for the first release.
- Show exactly which fields will be exported and whether values are masked.
- Default to masked evidence and metadata only.
- Include generated time, scan references, filters applied, and report scope.
- Do not claim that a report is a legal certification or formal audit opinion.

## 10. Components and interaction rules

Create a reusable design system with documented tokens and components:

- Button variants: primary, secondary, tertiary/ghost, destructive.
- Inputs: text, search, select, date range if needed, checkbox, switch, and textarea.
- Badges: status and confidence with consistent semantic mapping.
- Tables: header, row hover, selected state, empty state, loading state, pagination.
- Dialogs and drawers: consistent header, body, footer, close behaviour, and focus management.
- Toasts: concise success/error feedback; do not use toasts as the only way to convey important outcomes.
- Skeletons: match final content geometry and avoid layout jumps.
- Tooltips: use sparingly for abbreviations or technical terms.

Every visible control must work. Do not ship placeholder buttons, fake search, inert filters, or links to unfinished routes. If a capability is not implemented, omit it or label it clearly as unavailable in the development environment.

## 11. Content and microcopy

Use concise, operational language. Prefer labels such as:

- "Start scan"
- "Files processed"
- "Findings awaiting review"
- "Potential PAN match"
- "Masked evidence"
- "Mark as false positive"
- "Scan completed with errors"

Avoid vague phrases such as "Unlock insights", "Supercharge privacy", "AI-powered protection", or "Your security at a glance".

Use "potential match" or "detected pattern" rather than claiming an identifier is authentic. Use "exposure indicator" rather than "breach" unless a breach has actually been established.

## 12. Accessibility and responsive behaviour

- Target WCAG 2.2 AA contrast and interaction expectations.
- All controls must be keyboard accessible with visible focus.
- Use semantic headings, labels, landmarks, and table markup.
- Provide accessible names for icon-only controls.
- Do not encode status using colour alone.
- Respect reduced-motion preferences.
- Desktop-first for analyst workflows, but support tablet and narrow layouts without horizontal page overflow. Tables may use controlled horizontal scrolling where necessary.

## 13. Empty, loading, and error states

Every major page must have:

- A first-use empty state with a specific next action.
- A loading state that reflects the expected content shape.
- An error state with a useful explanation and retry path.
- A completed state that reports the actual result.

Examples:

- No sources: explain that an approved folder must be added before scanning.
- No discoveries: distinguish between "no scan has run" and "a completed scan returned no matches".
- Scan failed: show the failure reason without exposing local secrets or full file contents.

## 14. Demo data policy

- Seed data must be synthetic and clearly labelled **Demo data**.
- Never mix synthetic demo findings with real scan results without a persistent, visible distinction.
- No fake real-time activity, invented security incidents, or fabricated performance metrics.
- Provide a way to reset demo data in development only.

## 15. Quality bar

Before calling a UI screen complete, verify:

- It looks like one cohesive product, not a collection of unrelated templates.
- Spacing, typography, table density, controls, and statuses are consistent.
- Primary tasks are obvious without oversized callouts.
- The page remains useful with zero data, small data, and large data.
- All displayed figures come from the API or explicitly labelled synthetic seed data.
- No sensitive values leak into tables, URLs, browser logs, or notifications.
- The screen works at the target desktop width and at a narrower viewport.
