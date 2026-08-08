"""Build an index of DISPIMG images embedded in the local WPS xlsx workbook.

Outputs (all under <cache>/xlsx_image_index/):
  - images.tsv   : image_id | sheet_name | cell_addr | sheet_state | media_file | media_size | first_seen_order
  - summary.json : generation info and counts

Usage:
  python build_xlsx_image_index.py [--xlsx <path>] [--out <dir>]
  python build_xlsx_image_index.py --extract ID_E03B97595DA84E4A84753F5DF74BC49C --out <file>

The script is read-only for the source xlsx and only writes inside the cache.
"""

import argparse
import csv
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from kb_paths import cache_root

BASE = cache_root()
DEFAULT_XLSX_CANDIDATES = list(BASE.glob("日本站售后对应方案表*.xlsx"))
DEFAULT_OUT = BASE / "xlsx_image_index"

NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def col_to_number(addr: str) -> int:
    m = re.match(r"([A-Z]+)(\d+)", addr or "")
    if not m:
        return 0
    n = 0
    for ch in m.group(1):
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def parse_sheet_dispimg(sheet_xml: str):
    """Yield (cell_addr, image_id) for every DISPIMG cell in one sheet XML."""
    chunks = re.split(r"(?=<c\b)", sheet_xml)
    for chunk in chunks:
        cm = re.search(r'<c r="([A-Z]+\d+)"', chunk)
        if not cm or "_xlfn.DISPIMG" not in chunk:
            continue
        im = re.search(r"DISPIMG\(&quot;(ID_[0-9A-F]+)&quot;", chunk)
        if im:
            yield cm.group(1), im.group(1)


def parse_cellimages(cellimages_xml: str):
    """Map image_id -> rId from WPS cellimages.xml."""
    mapping = {}
    for block in re.findall(r"<etc:cellImage>(.*?)</etc:cellImage>", cellimages_xml, re.S):
        nm = re.search(r'name="(ID_[0-9A-F]+)"', block)
        em = re.search(r'r:embed="(rId\d+)"', block)
        if nm and em:
            mapping[nm.group(1)] = em.group(1)
    return mapping


def parse_rels_media(rels_xml: str):
    """Map rId -> media file path from a .rels file."""
    mapping = {}
    for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels_xml):
        target = m.group(2)
        if target.startswith("media/"):
            mapping[m.group(1)] = target
    return mapping


def build_index(xlsx: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    images_tsv = out_dir / "images.tsv"
    summary_json = out_dir / "summary.json"

    rows = []
    media_sizes = {}

    with zipfile.ZipFile(xlsx) as z:
        workbook_xml = z.read("xl/workbook.xml").decode("utf-8", "replace")
        workbook_rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8", "replace")

        sheet_rid_map = {}
        for m in re.finditer(
            r'<sheet name="([^"]*)"[^>]*?(?:state="([^"]*)")?[^>]*r:id="(rId\d+)"', workbook_xml
        ):
            sheet_rid_map[m.group(3)] = (m.group(1), m.group(2) or "visible")

        rid_target_map = {}
        for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', workbook_rels):
            rid_target_map[m.group(1)] = m.group(2)

        cellimages_id_rid = {}
        if "xl/cellimages.xml" in z.namelist():
            cellimages_xml = z.read("xl/cellimages.xml").decode("utf-8", "replace")
            cellimages_id_rid = parse_cellimages(cellimages_xml)
        rid_media = {}
        if "xl/_rels/cellimages.xml.rels" in z.namelist():
            rels_xml = z.read("xl/_rels/cellimages.xml.rels").decode("utf-8", "replace")
            rid_media = parse_rels_media(rels_xml)

        for info in z.infolist():
            if info.filename.startswith("xl/media/"):
                media_sizes[info.filename] = info.file_size

        order = 0
        seen_ids = set()
        for rid, (sheet_name, state) in sheet_rid_map.items():
            target = rid_target_map.get(rid, "")
            if not target.startswith("worksheets/") or not target.endswith(".xml"):
                continue
            try:
                sheet_xml = z.read("xl/" + target).decode("utf-8", "replace")
            except KeyError:
                continue
            for cell_addr, image_id in parse_sheet_dispimg(sheet_xml):
                order += 1
                seen_ids.add(image_id)
                rid2 = cellimages_id_rid.get(image_id, "")
                media = rid_media.get(rid2, "")
                rows.append(
                    {
                        "image_id": image_id,
                        "sheet_name": sheet_name,
                        "cell_addr": cell_addr,
                        "sheet_state": state,
                        "media_file": media,
                        "media_size": media_sizes.get("xl/" + media, 0) if media else 0,
                        "first_seen_order": order,
                    }
                )

        rows.sort(key=lambda r: (r["first_seen_order"], r["sheet_name"], col_to_number(r["cell_addr"])))

        with images_tsv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "image_id",
                    "sheet_name",
                    "cell_addr",
                    "sheet_state",
                    "media_file",
                    "media_size",
                    "first_seen_order",
                ],
                delimiter="\t",
            )
            writer.writeheader()
            writer.writerows(rows)

        sheets_with_images = {r["sheet_name"] for r in rows}
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "xlsx": str(xlsx),
            "xlsx_size": xlsx.stat().st_size,
            "unique_image_ids": len(seen_ids),
            "cell_references": len(rows),
            "sheets_with_images": len(sheets_with_images),
            "missing_media": sum(1 for r in rows if not r["media_file"]),
        }
        summary_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"done: {len(rows)} cell refs, {len(seen_ids)} unique images, {len(sheets_with_images)} sheets")
    for r in rows[:8]:
        print(f"  {r['sheet_name']} {r['cell_addr']} {r['image_id']} -> {r['media_file']}")
    return rows


def extract_image(xlsx: Path, image_id: str, out_file: Path):
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(xlsx) as z:
        cellimages_xml = z.read("xl/cellimages.xml").decode("utf-8", "replace")
        id_rid = parse_cellimages(cellimages_xml)
        rid = id_rid.get(image_id)
        if not rid:
            print(f"NOT_FOUND: {image_id}")
            return 1
        rels_xml = z.read("xl/_rels/cellimages.xml.rels").decode("utf-8", "replace")
        rid_media = parse_rels_media(rels_xml)
        media = rid_media.get(rid)
        if not media:
            print(f"NO_MEDIA: {image_id} ({rid})")
            return 1
        with z.open("xl/" + media) as src, out_file.open("wb") as dst:
            dst.write(src.read())
    print(f"EXTRACTED: {out_file} ({out_file.stat().st_size} bytes) from {media}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", default=str(DEFAULT_XLSX_CANDIDATES[0]) if DEFAULT_XLSX_CANDIDATES else "")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--extract", default="")
    args = parser.parse_args()

    xlsx = Path(args.xlsx)
    if not xlsx.exists():
        print(f"ERROR: xlsx not found: {xlsx}")
        return 2

    if args.extract:
        return extract_image(xlsx, args.extract, Path(args.out))
    build_index(xlsx, Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
