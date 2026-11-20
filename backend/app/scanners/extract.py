"""Bounded document extraction subprocess. Input and output stay in pipes."""

import csv
from io import BytesIO, StringIO
import json
import resource
import sys
from zipfile import ZipFile

TEXT_LIMIT = 1_000_000
MAX_PDF_PAGES = 200
MAX_WORKBOOK_CELLS = 100_000
MAX_ARCHIVE_ENTRIES = 1_000
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024


class ExtractionLimit(ValueError):
    pass


class EncryptedDocument(ValueError):
    pass


def pdf_fragments(data: bytes):
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as document:
        if document.needs_pass:
            raise EncryptedDocument
        if document.page_count > MAX_PDF_PAGES:
            raise ExtractionLimit
        for page in document:
            yield page.get_text()


def workbook_fragments(data: bytes):
    from openpyxl import load_workbook

    with ZipFile(BytesIO(data)) as archive:
        members = archive.infolist()
        if (
            len(members) > MAX_ARCHIVE_ENTRIES
            or sum(member.file_size for member in members) > MAX_UNCOMPRESSED_BYTES
        ):
            raise ExtractionLimit
        if any(member.flag_bits & 1 for member in members):
            raise EncryptedDocument
    workbook = load_workbook(
        BytesIO(data), read_only=True, data_only=True, keep_links=False, keep_vba=False
    )
    try:
        cells = 0
        for sheet in workbook.worksheets:
            sheet.reset_dimensions()
            for row in sheet.values:
                cells += max(1, len(row))
                if cells > MAX_WORKBOOK_CELLS:
                    raise ExtractionLimit
                yield "\t".join(str(value) for value in row if value is not None)
    finally:
        workbook.close()


def json_fragments(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (str, int, float)):
                yield f"{key}: {item}"
            else:
                yield from json_fragments(item)
    elif isinstance(value, list):
        for item in value:
            yield from json_fragments(item)
    elif isinstance(value, (str, int, float)):
        yield str(value)


def fragments(extension: str, data: bytes):
    if extension == ".pdf":
        yield from pdf_fragments(data)
        return
    if extension in {".xlsx", ".xlsm"}:
        yield from workbook_fragments(data)
        return
    text = data.decode("utf-8-sig")
    if extension == ".csv":
        for row in csv.reader(StringIO(text, newline=""), strict=True):
            yield "\t".join(row)
    elif extension == ".json":
        yield from json_fragments(json.loads(text))
    elif extension in {".txt", ".log"}:
        yield text
    else:
        raise ValueError


def main() -> int:
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    size_limit = int(sys.argv[2])
    try:
        data = sys.stdin.buffer.read(size_limit + 1)
        if len(data) > size_limit:
            return 2
        output = bytearray()
        for fragment in fragments(sys.argv[1], data):
            encoded = fragment.encode("utf-8")
            if len(output) + len(encoded) + 1 > TEXT_LIMIT:
                return 2
            output.extend(encoded)
            output.append(10)
        sys.stdout.buffer.write(output)
    except EncryptedDocument:
        return 3
    except MemoryError:
        return 2
    except ExtractionLimit:
        return 2
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
