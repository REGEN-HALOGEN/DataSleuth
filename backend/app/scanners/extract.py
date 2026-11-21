"""Bounded document extraction subprocess. Input and output stay in pipes."""

import codecs
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


def validate_upload(extension: str, handle, limit: int):
    # Upload scratch is seekable. Read only the bytes needed to identify the type.
    if handle.seek(0, 2) > limit:
        raise ExtractionLimit
    handle.seek(0)
    prefix = handle.read(5)
    handle.seek(0)
    if extension == ".pdf":
        if prefix != b"%PDF-":
            raise ValueError
    elif extension in {".xlsx", ".xlsm"}:
        from defusedxml.ElementTree import fromstring

        with ZipFile(handle) as archive:
            manifest = archive.getinfo("[Content_Types].xml")
            if (
                len(archive.infolist()) > MAX_ARCHIVE_ENTRIES
                or manifest.file_size > 256 * 1024
            ):
                raise ExtractionLimit
            root = fromstring(archive.read(manifest))
            expected = (
                "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
                if extension == ".xlsm"
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
            )
            if not any(
                node.get("ContentType") == expected
                and node.get("PartName") == "/xl/workbook.xml"
                for node in root
            ):
                raise ValueError
    elif extension == ".json":
        json.loads(handle.read(limit + 1).decode("utf-8-sig"))
    else:
        if prefix.startswith((b"%PDF-", b"PK\x03\x04")):
            raise ValueError
        decoder = codecs.getincrementaldecoder("utf-8-sig")()
        while chunk := handle.read(64 * 1024):
            if b"\x00" in chunk:
                raise ValueError
            decoder.decode(chunk)
        decoder.decode(b"", final=True)


def main() -> int:
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    size_limit = int(sys.argv[2])
    try:
        if sys.argv[3:] == ["validate"]:
            validate_upload(sys.argv[1], sys.stdin.buffer, size_limit)
            return 0
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
