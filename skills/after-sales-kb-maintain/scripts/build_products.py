"""Build products.tsv mapping product -> FAQ / OCR texts / page dirs / videos."""
import csv
import json
import re
from kb_paths import cache_root

BASE = cache_root()
KDOCS = BASE / "kdocs"
FAQ = BASE / "faq"
OCR = BASE / "pdf_ocr"
PAGES = BASE / "pdf_pages"
VIDEO_TSV = BASE / "video_index" / "videos.tsv"
OUT = BASE / "products.tsv"


def load_videos():
    videos = []
    if not VIDEO_TSV.exists():
        return videos
    for line in VIDEO_TSV.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        videos.append(parts[0])
    return videos


def sheet_keywords(sheet: str):
    """Derive search keywords from a sheet name."""
    # Remove an internal owner or variant suffix in full-width parentheses.
    name = re.sub(r"[（(].*?[）)]", "", sheet)
    name = name.strip()
    keywords = []
    # Full name pieces
    for part in re.split(r"[-—&_]", name):
        part = part.strip()
        if part and len(part) >= 2:
            keywords.append(part)
    # Alphanumeric model codes (e.g. P10, 8016, XD-1586FB)
    for m in re.finditer(r"[A-Za-z0-9]+[-]?[A-Za-z0-9]*", name):
        code = m.group(0)
        if len(code) >= 3:
            keywords.append(code)
    return sorted(set(keywords), key=len, reverse=True)


def match_ocr(keywords, sheet):
    """Find OCR txt files matching product keywords (by filename or parent dir hints)."""
    hits = []
    for txt in sorted(OCR.glob("*.txt")):
        low = txt.stem.lower()
        if any(k.lower() in low for k in keywords if len(k) >= 2):
            hits.append(txt.name)
    return hits


def match_pages(keywords):
    """Find pdf_pages relative directories matching product keywords."""
    hits = []
    for d in sorted(PAGES.rglob("*")):
        if d.is_dir():
            continue
        rel = d.relative_to(PAGES)
        low = str(rel).lower()
        if any(k.lower() in low for k in keywords if len(k) >= 2):
            hits.append(str(rel))
    return hits


def match_videos(keywords, videos):
    hits = []
    for v in videos:
        low = v.lower()
        if any(k.lower() in low for k in keywords if len(k) >= 2):
            hits.append(v)
    return hits


def pdf_basename_to_dirs():
    """Map PDF basename -> set of page-image relative dirs (from pdf_pages)."""
    mapping = {}
    for p in sorted(PAGES.rglob("*")):
        if p.is_dir():
            continue
        if not p.name.lower().endswith(".jpg"):
            continue
        # filename like "XXX_p-1.jpg"; strip page suffix
        stem = p.stem
        base = re.sub(r"_p-\d+$", "", stem)
        rel = str(p.relative_to(PAGES))
        mapping.setdefault(base, set()).add(rel)
    return mapping


def match_ocr_via_pages(keywords, basename_dirs):
    """Find OCR txt files whose underlying PDF lives under a matching dir."""
    hits = []
    for base, dirs in basename_dirs.items():
        low = " ".join(dirs).lower()
        if any(k.lower() in low for k in keywords if len(k) >= 2):
            txt = OCR / f"{base}.txt"
            if txt.exists():
                hits.append(txt.name)
    return hits


DEFAULT_ALIASES = {
    "switch手柄": ["switch手柄", "sw手柄", "switch", "sw", "06手柄", "05手柄", "03手柄", "pro手柄"],
    "ps4手柄": ["ps4", "p4", "p4手柄", "ps4手柄", "playstation"],
    "ds-100熨斗": ["机械熨斗", "ds-100", "ds100", "熨斗"],
    "ds-700熨斗": ["ds-700", "ds700", "熨斗"],
    "lm-026熨斗": ["lm-026", "lm026", "熨斗", "蒸汽熨斗"],
}


def load_aliases():
    aliases = dict(DEFAULT_ALIASES)
    path = BASE / "product_aliases.json"
    if path.exists():
        try:
            local = json.loads(path.read_text(encoding="utf-8-sig"))
            for key, values in local.items():
                if isinstance(values, list):
                    aliases[key.lower()] = [str(v) for v in values if str(v).strip()]
        except (OSError, ValueError):
            pass
    return aliases


def aliases_for_sheet(sheet: str, aliases: dict):
    normalized = re.sub(r"[（(].*?[）)]", "", sheet).strip().lower()
    values = []
    for key, items in aliases.items():
        if key in normalized or normalized in key:
            values.extend(items)
    return values


def main():
    videos = load_videos()
    aliases = load_aliases()
    basename_dirs = pdf_basename_to_dirs()
    sheets = sorted(f.stem for f in KDOCS.glob("*.txt") if f.name != "_capture_log.txt")
    rows = []
    for sheet in sheets:
        keywords = set(sheet_keywords(sheet))
        keywords.update(aliases_for_sheet(sheet, aliases))
        faq_file = f"{sheet}.json"
        ocr_files = match_ocr(keywords, sheet)
        ocr_files += match_ocr_via_pages(keywords, basename_dirs)
        ocr_files = sorted(set(ocr_files))
        page_files = match_pages(keywords)
        video_files = match_videos(keywords, videos)
        rows.append({
            "product": sheet,
            "keywords": "|".join(keywords),
            "faq": faq_file,
            "ocr_count": len(ocr_files),
            "ocr_files": "|".join(ocr_files[:8]),
            "page_count": len(page_files),
            "pages": "|".join(page_files[:8]),
            "video_count": len(video_files),
            "videos": "|".join(video_files[:6]),
        })
    fieldnames = [
        "product", "keywords", "faq", "ocr_count", "ocr_files",
        "page_count", "pages", "video_count", "videos",
    ]
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print(f"done: {len(rows)} products -> {OUT}")
    for r in rows[:10]:
        print(f"{r['product']}: faq={r['faq']} ocr={r['ocr_count']} pages={r['page_count']} videos={r['video_count']}")


if __name__ == "__main__":
    main()
