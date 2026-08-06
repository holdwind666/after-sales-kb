"""Build products.tsv mapping product -> FAQ / OCR texts / page dirs / videos."""
import csv
import json
import re
from pathlib import Path

BASE = Path(r"E:\说明书与视频（第9台）\_售后模板缓存")
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
    # Remove owner suffix like （楚腾飞）
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


ALIASES = {
    "switch手柄（楚腾飞）": ["switch手柄", "sw手柄", "switch", "sw", "06手柄", "05手柄", "03手柄", "065", "064", "038", "pro手柄"],
    "PS4手柄（楚腾飞）": ["ps4", "p4", "p4手柄", "ps4手柄", "ps5", "playstation"],
    "DS-100熨斗（魏子奇）机械白-机械灰": ["机械熨斗", "ds-100", "ds100", "机械白", "机械灰", "熨斗"],
    "DS-700熨斗（肖湘-白金）": ["白金熨斗", "ds-700", "ds700", "熨斗"],
    "LM-026熨斗（杨怡）": ["lm-026", "lm026", "熨斗", "蒸汽熨斗"],
    "手持小熨斗（林小君-灰色）": ["手持小熨斗", "小熨斗", "灰色熨斗"],
    "机械熨斗说明书（转曲）1000W": ["机械熨斗", "1000w"],
}


def main():
    videos = load_videos()
    basename_dirs = pdf_basename_to_dirs()
    sheets = sorted(f.stem for f in KDOCS.glob("*.txt") if f.name != "_capture_log.txt")
    rows = []
    for sheet in sheets:
        keywords = set(sheet_keywords(sheet))
        keywords.update(ALIASES.get(sheet, []))
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
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print(f"done: {len(rows)} products -> {OUT}")
    for r in rows[:10]:
        print(f"{r['product']}: faq={r['faq']} ocr={r['ocr_count']} pages={r['page_count']} videos={r['video_count']}")


if __name__ == "__main__":
    main()
