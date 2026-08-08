"""Build a lightweight knowledge-graph layer over the cached KB.

The KB graph is deterministic (no embeddings/API): it links every product to
its FAQ sheet, OCR manuals, spec files, parameter pages, page images and demo
videos, then exports node/edge TSVs plus a summary. It is used for:

  - validating that the index build captured all sources (gap detection),
  - showing which sources a query could fall back to before giving up,
  - answering "which documents contain product X" in one lookup.

Outputs (under <cache>/kb_graph/):
  - nodes.tsv      : id, kind, label, path
  - edges.tsv      : src, dst, rel
  - summary.json   : counts + products missing FAQ/OCR/spec/video

Read-only: reads products.tsv, faq/, kdocs/, pdf_ocr/, pdf_pages/,
video_index/, quick_index/. Writes only kb_graph/.
"""

import csv
import json
import re
from datetime import datetime, timezone
from kb_paths import cache_root

BASE = cache_root()
PRODUCTS_TSV = BASE / "products.tsv"
FAQ_DIR = BASE / "faq"
KDOCS_DIR = BASE / "kdocs"
OCR_DIR = BASE / "pdf_ocr"
PAGES_DIR = BASE / "pdf_pages"
VIDEO_TSV = BASE / "video_index" / "videos.tsv"
SPEC_INDEX = BASE / "quick_index" / "spec_norm.tsv"
PARAM_INDEX = BASE / "quick_index" / "params_norm.tsv"
OUT_DIR = BASE / "kb_graph"


def norm_key(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def load_products() -> list[dict]:
    rows = []
    if not PRODUCTS_TSV.exists():
        return rows
    lines = PRODUCTS_TSV.read_text(encoding="utf-8").splitlines()
    if not lines:
        return rows
    header = lines[0].split("\t")
    for line in lines[1:]:
        parts = line.split("\t")
        row = {}
        for i, key in enumerate(header):
            row[key] = parts[i] if i < len(parts) else ""
        rows.append(row)
    return rows


def match_keywords(row: dict, path_text: str) -> bool:
    kws = [k for k in row.get("keywords", "").split("|") if len(k) >= 2]
    npath = norm_key(path_text)
    return any(norm_key(k) in npath for k in kws)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    products = load_products()
    nodes: list[list[str]] = []
    edges: list[list[str]] = []
    seen_nodes: set[str] = set()

    def node(nid: str, kind: str, label: str, path: str = ""):
        if nid in seen_nodes:
            return
        seen_nodes.add(nid)
        nodes.append([nid, kind, label, path])

    def edge(src: str, dst: str, rel: str):
        if (src, dst, rel) not in edges:
            edges.append([src, dst, rel])

    # Fixed tables as graph nodes
    for kdoc in sorted(KDOCS_DIR.glob("*.txt")):
        if kdoc.name == "_capture_log.txt":
            continue
        nid = "table:" + kdoc.stem
        node(nid, "table", kdoc.stem, "kdocs/" + kdoc.name)

    # Spec files already indexed
    spec_by_norm: dict[str, str] = {}
    if SPEC_INDEX.exists():
        for line in SPEC_INDEX.read_text(encoding="utf-8").splitlines():
            if "\t" not in line:
                continue
            name, _ = line.split("\t", 1)
            spec_by_norm[norm_key(name)] = name

    # Parameter pages
    param_by_file: dict[str, set[str]] = {}
    if PARAM_INDEX.exists():
        for line in PARAM_INDEX.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            param_by_file.setdefault(parts[0], set()).add(parts[1] or "-")

    # Page images + videos
    pages_by_dir: dict[str, list[str]] = {}
    if PAGES_DIR.exists():
        for p in sorted(PAGES_DIR.rglob("*")):
            if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png"):
                rel = str(p.relative_to(PAGES_DIR))
                top = rel.split("\\")[0] if "\\" in rel else rel.split("/")[0]
                pages_by_dir.setdefault(top, []).append(rel)

    videos: list[str] = []
    if VIDEO_TSV.exists():
        for line in VIDEO_TSV.read_text(encoding="utf-8").splitlines():
            if line.strip():
                videos.append(line.split("\t")[0])

    for row in products:
        pid = "product:" + row.get("product", "")
        node(pid, "product", row.get("product", ""))

        faq = row.get("faq", "")
        if faq:
            fid = "faq:" + faq
            node(fid, "faq", faq, "faq/" + faq)
            edge(pid, fid, "has_faq")

        for ocr_name in [x for x in row.get("ocr_files", "").split("|") if x]:
            oid = "ocr:" + ocr_name
            node(oid, "ocr", ocr_name, "pdf_ocr/" + ocr_name)
            edge(pid, oid, "has_manual")

        for page_rel in [x for x in row.get("pages", "").split("|") if x][:20]:
            pid_img = "page:" + page_rel
            node(pid_img, "page", page_rel.split("\\")[-1], "pdf_pages/" + page_rel)
            edge(pid, pid_img, "has_page")

        for video in [x for x in row.get("videos", "").split("|") if x]:
            vid = "video:" + video
            node(vid, "video", video.split("\\")[-1], video)
            edge(pid, vid, "has_video")

        # spec/param linkage by filename keywords
        nprod = norm_key(row.get("product", ""))
        for rel, _ in spec_by_norm.items():
            if nprod and (norm_key(rel.split("\\")[-1]) in nprod or nprod in norm_key(rel)):
                sid = "spec:" + rel
                node(sid, "spec", rel.split("\\")[-1], rel)
                edge(pid, sid, "has_spec")
        for file_key, pages in param_by_file.items():
            if nprod and (norm_key(file_key) in nprod or nprod in norm_key(file_key)):
                pid_p = "params:" + file_key
                node(pid_p, "params", file_key, "quick_index/params_norm.tsv")
                edge(pid, pid_p, "has_params")

        # kdocs table linkage by product keywords
        for t in sorted(KDOCS_DIR.glob("*.txt")):
            if t.name == "_capture_log.txt":
                continue
            tid = "table:" + t.stem
            if match_keywords(row, t.stem):
                node(tid, "table", t.stem, "kdocs/" + t.name)
                edge(pid, tid, "related_table")

    with (OUT_DIR / "nodes.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["id", "kind", "label", "path"])
        w.writerows(nodes)
    with (OUT_DIR / "edges.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["src", "dst", "rel"])
        w.writerows(edges)

    kinds: dict[str, int] = {}
    for n in nodes:
        kinds[n[1]] = kinds.get(n[1], 0) + 1
    missing = {
        "no_faq": [r.get("product", "") for r in products if not r.get("faq")],
        "no_ocr": [r.get("product", "") for r in products if not r.get("ocr_files")],
        "no_video": [r.get("product", "") for r in products if not r.get("videos")],
    }
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "node_kinds": kinds,
        "edge_count": len(edges),
        "product_count": len(products),
        "missing": missing,
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
