"""One-off migration: renumber OCR page markers sequentially.

The old ocr_worker.ps1 wrote '===== PAGE 1 =====, 3, 5, ...' because it
appended two entries per page. The marker value is therefore not the real
PDF page number and page-level hits were off by one. This script rewrites
every '===== PAGE N =====' marker to 1..K sequentially for all OCR text
files, preserving all content. Run once, then rebuild the quick index and
the manual-image association index.

Usage:
  python migrate_ocr_page_markers.py            # migrate all pdf_ocr/*.txt
  python migrate_ocr_page_markers.py --dry-run  # only report what would change
"""

import argparse
import re
from kb_paths import cache_root

BASE = cache_root()
OCR_DIR = BASE / "pdf_ocr"

PAGE_RE = re.compile(r"(?m)^===== PAGE (\d+) =====\s*$")


def migrate_text(text: str) -> str | None:
    matches = list(PAGE_RE.finditer(text))
    if not matches:
        return None
    # Old markers are always odd (1,3,5,...); verify before rewriting.
    vals = [int(m.group(1)) for m in matches]
    if all(v % 2 == 1 for v in vals):
        count = len(vals)
        out = []
        last = 0
        for i, m in enumerate(matches):
            out.append(text[last : m.start()])
            out.append(f"===== PAGE {i + 1} =====")
            last = m.end()
        out.append(text[last:])
        return "".join(out)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    changed = 0
    for p in sorted(OCR_DIR.glob("*.txt")):
        original = p.read_text(encoding="utf-8", errors="replace")
        migrated = migrate_text(original)
        if migrated is None or migrated == original:
            continue
        changed += 1
        if not args.dry_run:
            p.write_text(migrated, encoding="utf-8", newline="")
        print(f"{p.name}: markers migrated")
    print(f"MIGRATED={changed} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
