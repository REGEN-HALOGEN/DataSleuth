"""Generate a new folder of clearly labelled DataSleuth demo documents."""

import argparse
import csv
import json
import os
from pathlib import Path

import openpyxl
import pymupdf

DEMO_LABEL = "Demo data"
DEMO_EMAIL = "inventory-demo@example.invalid"
DEMO_FALSE_POSITIVE = "ZZZPZ0000Z"


def write_demo(output: Path, max_file_size: int) -> None:
    output.mkdir()
    (output / "demo-notes.txt").write_text(
        f"{DEMO_LABEL}\nEmail: {DEMO_EMAIL}\n"
        f"Fictional inventory code: {DEMO_FALSE_POSITIVE}\n",
        encoding="utf-8",
    )
    with (output / "demo-contacts.csv").open(
        "x", encoding="utf-8", newline=""
    ) as stream:
        csv.writer(stream).writerows([("label", "email"), (DEMO_LABEL, DEMO_EMAIL)])
    (output / "demo-record.json").write_text(
        json.dumps({"label": DEMO_LABEL, "email": DEMO_EMAIL}, indent=2) + "\n",
        encoding="utf-8",
    )

    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), f"{DEMO_LABEL}\nEmail: {DEMO_EMAIL}")
        document.save(output / "demo-document.pdf")
    workbook = openpyxl.Workbook()
    try:
        workbook.active.title = DEMO_LABEL
        workbook.active.append(["Label", "Email"])
        workbook.active.append([DEMO_LABEL, DEMO_EMAIL])
        workbook.save(output / "demo-sheet.xlsx")
    finally:
        workbook.close()

    (output / "demo-unsupported.bin").write_bytes(b"DataSleuth demo data")
    with (output / "demo-oversized.log").open("xb") as stream:
        stream.truncate(max_file_size + 1)
    (output / "demo-malformed.json").write_text('{"demo":', encoding="utf-8")
    unreadable = output / "demo-unreadable.txt"
    unreadable.write_text("Demo data. Permission fixture.", encoding="utf-8")
    if os.name == "posix":
        unreadable.chmod(0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output", type=Path, help="A new folder under an existing directory"
    )
    parser.add_argument("--max-file-size-bytes", type=int, default=10 * 1024**2)
    args = parser.parse_args()
    if not 64 * 1024 <= args.max_file_size_bytes <= 32 * 1024**2:
        parser.error("Choose a file limit from 64 KiB through 32 MiB.")
    try:
        write_demo(args.output, args.max_file_size_bytes)
    except FileExistsError:
        raise SystemExit("Choose a new output directory.") from None
    except OSError:
        raise SystemExit(
            "Could not write the demo folder. Check the parent directory and permissions."
        ) from None
    print(f"Created synthetic fixtures in {args.output.absolute()}")
    print(
        'Register the folder with the source name "Demo data" in a disposable development instance.'
    )
    if os.access(args.output / "demo-unreadable.txt", os.R_OK):
        print("This filesystem or user permits reading the permission fixture.")


if __name__ == "__main__":
    main()
