# Synthetic acceptance demo

Use a disposable development database and Redis instance. Generate the fixture
on the WSL filesystem as an unprivileged user so normal file permissions apply.
The generator creates a new directory and preserves any existing directory.

From the repository root after setting up the backend environment:

```bash
demo_parent=$(mktemp -d)
.venv-linux/bin/python scripts/seed_demo.py "$demo_parent/synthetic"
```

For a nondefault file-size limit, pass
`--max-file-size-bytes <value>` to match `MAX_FILE_SIZE_BYTES`. Use the
generated absolute path in the JSON list `ALLOWED_SCAN_ROOTS` for the demo
instance. Start the stack with `bash start.sh` on WSL, then register the
folder in **Scan Sources** with the name **Demo data**.

1. Start a read-only scan of **Demo data** and open **Scan History**.
2. Expect nine files, five processed, two skipped, and two failed when
   the permission fixture is unreadable. If the current user can read that
   file, expect six processed and one failed instead. Both cases produce six
   findings. The oversized and unsupported fixtures are skipped, and the
   malformed JSON fixture fails.
3. Open the scan's findings and filter for email with confidence at least
   90%. Five findings should appear. Open one and verify the evidence is
   redacted and four related occurrences are listed.
4. Confirm an email finding. Review the fictional inventory code detected
   as a PAN-shaped value and mark it as a false positive. Check the review
   history on both.
5. Export the scan in CSV and JSON from **Reports**. Check for six finding
   records, the scan reference, the chosen review statuses, and redacted
   evidence.
6. Restart the app against the same demo database and verify Scan History
   and both review decisions are still present.

Use a new disposable database and a new output directory to start a clean demo.
On Windows PowerShell, the generator can also run with
`.\.venv\Scripts\python.exe scripts\seed_demo.py <new-directory>`.
Use the corresponding absolute WSL path for scanning. File permissions on
Windows-mounted drives may allow the permission fixture to be read.
