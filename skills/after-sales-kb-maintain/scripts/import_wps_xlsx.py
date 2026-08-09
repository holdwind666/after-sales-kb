#!/usr/bin/env python3
"""Convert a local WPS/Excel workbook into one UTF-8 text file per sheet.

The output matches the tab/newline format consumed by build_faq_index.py.
Only the Python standard library is used so first-time setup does not need
openpyxl or a cloud API.
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS, "p": PKG_REL_NS}


def safe_name(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", value).strip().rstrip(".")
    return cleaned or "Sheet"


def column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref.upper())
    if not letters:
        return 0
    result = 0
    for char in letters.group(0):
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def shared_strings(book: zipfile.ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in book.namelist():
        return []
    root = ET.fromstring(book.read(path))
    values: list[str] = []
    for item in root.findall("m:si", NS):
        values.append("".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t")))
    return values


def sheet_targets(book: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("p:Relationship", NS)
    }
    result: list[tuple[str, str]] = []
    for sheet in workbook.findall("m:sheets/m:sheet", NS):
        rid = sheet.attrib.get(f"{{{REL_NS}}}id", "")
        target = rel_map.get(rid, "")
        if not target:
            continue
        target = target.replace("\\", "/").lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        result.append((sheet.attrib.get("name", "Sheet"), target))
    return result


def cell_value(cell: ET.Element, strings: list[str]) -> str:
    kind = cell.attrib.get("t", "")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
    value = cell.find("m:v", NS)
    raw = value.text if value is not None and value.text is not None else ""
    if kind == "s" and raw.isdigit():
        index = int(raw)
        return strings[index] if index < len(strings) else ""
    if kind == "b":
        return "TRUE" if raw == "1" else "FALSE"
    return raw


def sheet_text(book: zipfile.ZipFile, target: str, strings: list[str]) -> str:
    root = ET.fromstring(book.read(target))
    lines: list[str] = []
    for row in root.findall("m:sheetData/m:row", NS):
        values: dict[int, str] = {}
        for cell in row.findall("m:c", NS):
            values[column_index(cell.attrib.get("r", "A1"))] = cell_value(cell, strings)
        if not values:
            continue
        last = max(values)
        cells = [values.get(index, "").replace("\t", " ").replace("\r", " ").replace("\n", " ") for index in range(last + 1)]
        lines.append("\t".join(cells).rstrip("\t"))
    return "\n".join(lines).strip() + "\n" if lines else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source = Path(args.source)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        print(f"XLSX_MISSING={source}")
        return 2

    written = skipped = empty = 0
    with zipfile.ZipFile(source) as book:
        strings = shared_strings(book)
        for sheet_name, target in sheet_targets(book):
            text = sheet_text(book, target, strings)
            if not text.strip():
                empty += 1
                continue
            destination = out_dir / f"{safe_name(sheet_name)}.txt"
            if destination.exists() and destination.stat().st_size > 50 and not args.force:
                skipped += 1
                continue
            destination.write_text(text, encoding="utf-8")
            written += 1
            print(f"WPS_SHEET={sheet_name}|{destination}")
    print(f"WPS_IMPORT_DONE written={written} skipped={skipped} empty={empty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
