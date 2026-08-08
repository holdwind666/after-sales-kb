"""Generate a knowledge-gap report for the after-sales KB.

Mirrors WorkBuddy phase 4/6: identify expired/weak/missing content so
maintainers can prioritize updates. Outputs:
  - gaps/gap_report.tsv : one row per gap (type | product/file | detail)
  - gaps/gap_report.md  : human-readable summary

Gap types:
  - empty_ocr      : OCR text normalized length < 200 (likely unreadable pages)
  - no_faq         : product has no FAQ JSON or zero items
  - no_ocr         : product has no OCR files mapped
  - miss_record    : unanswered questions recorded in miss_counter.json
"""

import json
import re
import sys
from datetime import datetime, timezone
from kb_paths import cache_root

BASE = cache_root()
OCR_DIR = BASE / "pdf_ocr"
FAQ_DIR = BASE / "faq"
PRODUCTS_TSV = BASE / "products.tsv"
MISS_COUNTER = BASE / "miss_counter.json"
OUT_DIR = BASE / "gaps"

EMPTY_THRESHOLD = 200


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gaps = []  # (type, subject, detail)

    # 1) empty / near-empty OCR files
    for p in sorted(OCR_DIR.glob("*.txt")):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
        n = len(norm(text))
        if n < EMPTY_THRESHOLD:
            gaps.append(("empty_ocr", p.name, f"normalized_len={n}"))

    # 2) products with no FAQ or empty FAQ
    products = []
    if PRODUCTS_TSV.exists():
        lines = PRODUCTS_TSV.read_text(encoding="utf-8").splitlines()
        header = lines[0].split("\t")
        try:
            ip = header.index("product")
            ifq = header.index("faq")
            iocr = header.index("ocr_files")
        except ValueError:
            ip = ifq = iocr = 0
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) <= max(ip, ifq, iocr):
                continue
            products.append(
                (parts[ip], parts[ifq], [x for x in parts[iocr].split("|") if x])
            )
    for name, faq_file, ocr_files in products:
        if not faq_file or not (FAQ_DIR / faq_file).exists():
            gaps.append(("no_faq", name, f"missing faq file: {faq_file}"))
            continue
        try:
            data = json.loads((FAQ_DIR / faq_file).read_text(encoding="utf-8"))
            n_items = len(data.get("items", []))
        except Exception:
            n_items = 0
        if n_items == 0:
            gaps.append(("no_faq", name, "faq has zero items"))
        if not ocr_files:
            gaps.append(("no_ocr", name, "no OCR files mapped"))

    # 3) unanswered questions from miss counter
    if MISS_COUNTER.exists():
        try:
            miss = json.loads(MISS_COUNTER.read_text(encoding="utf-8"))
            for r in miss.get("records", []):
                gaps.append(
                    (
                        "miss_record",
                        r.get("product", "-"),
                        f"{r.get('question','-')} | {r.get('reason','-')}",
                    )
                )
        except Exception:
            pass

    # write TSV
    tsv = OUT_DIR / "gap_report.tsv"
    with tsv.open("w", encoding="utf-8", newline="") as f:
        f.write("type\tsubject\tdetail\n")
        for g in sorted(gaps):
            f.write("\t".join(g) + "\n")

    # write MD summary
    counts = {}
    for g in gaps:
        counts[g[0]] = counts.get(g[0], 0) + 1
    md = OUT_DIR / "gap_report.md"
    lines = [
        "# 知识库缺口报告",
        "",
        f"生成时间: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        "## 汇总",
        "",
    ]
    for k in sorted(counts):
        lines.append(f"- {k}: {counts[k]}")
    lines += ["", "## 明细", ""]
    for g in sorted(gaps):
        lines.append(f"- [{g[0]}] {g[1]} — {g[2]}")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(counts, ensure_ascii=False))
    print(f"TOTAL_GAPS={len(gaps)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
