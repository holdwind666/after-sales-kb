"""Hybrid retrieval for the after-sales knowledge base.

Usage:
  python quick_query.py --product "电热毯" --q "包装内容"
  python quick_query.py --product "V10" --q "线长"
  python quick_query.py --q "充電できない"
  python quick_query.py --product "电热毯" --q "包装内容" --diagnose

Retrieval pipeline:
  1. Synonym expansion (quick_index/synonyms.tsv, data-driven).
  2. Exact normalized substring match on page-grained OCR / FAQ / kdocs / spec.
  3. Fuzzy scoring (rapidfuzz partial_ratio) for near-miss recall.
  4. BM25 ranking (rank_bm25) over the same rows for relevance.
  Final rank: exact > fuzzy*0.95 > bm25; deduped per (layer, doc, page).

--diagnose: when nothing is found, inspect the layer pipeline and report
where content may be lost (OCR page lengths, source PDF text layer status,
page images for on-demand vision).
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

from kb_paths import cache_root, data_root, load_config

BASE = cache_root()
OUT_DIR = BASE / "quick_index"
OCR_DIR = BASE / "pdf_ocr"
PAGES_DIR = BASE / "pdf_pages"
SOURCE_ROOT = data_root()
CHATGPT_CFG = BASE / "chatgpt_learning.json"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def load_synonyms():
    """Load zh->ja synonym dictionary from quick_index/synonyms.tsv."""
    p = OUT_DIR / "synonyms.tsv"
    syn = {}
    if not p.exists():
        return syn
    for line in p.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            syn[parts[0]] = parts[1:]
    return syn


def query_terms(q: str):
    qn = norm(q)
    terms = [qn]
    syn = load_synonyms()
    # Phrase-level expansion: every synonym key that appears inside the query
    # contributes its zh/ja expansions. E.g. "电源线 长度" expands to
    # 電源コード長 / 電源側コード長 / 本体側コード長 even when the full
    # query string has no exact synonym entry.
    for zh, ja_list in syn.items():
        nzh = norm(zh)
        if nzh and nzh in qn:
            for ja in ja_list:
                nja = norm(ja)
                if nja:
                    terms.append(nja)
    # reverse mapping: a Japanese term inside the query also maps back
    for zh, ja_list in syn.items():
        nzh = norm(zh)
        if not nzh or nzh in terms:
            continue
        for ja in ja_list:
            if norm(ja) in qn:
                terms.append(nzh)
                break
    return list(dict.fromkeys(t for t in terms if t))


def tokenize(s: str):
    """Lightweight tokenizer: ascii words + CJK bigrams + whole string."""
    s = norm(s)
    toks = []
    ascii_part = re.sub(r"[^\x00-\x7f]+", " ", s).split()
    toks.extend(ascii_part)
    cjk = re.sub(r"[\x00-\x7f]+", "", s)
    for i in range(len(cjk) - 1):
        toks.append(cjk[i : i + 2])
    if cjk:
        toks.append(cjk)
    return toks


def load_rows(kind: str):
    p = OUT_DIR / f"{kind}_norm.tsv"
    rows = []
    if not p.exists():
        return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        if "\t" in line:
            name, blob = line.split("\t", 1)
            rows.append((name, blob))
    return rows


def load_faq_full():
    """Load faq_full.jsonl: list of dicts {sheet, question, answer, template}."""
    p = OUT_DIR / "faq_full.jsonl"
    items = []
    if not p.exists():
        return items
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return items


def load_faq_lookup():
    """Load precompiled faq_lookup.json (product -> entries with keys)."""
    p = OUT_DIR / "faq_lookup.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def lookup_faq_fast(lookup, product, q, terms):
    """Fast dictionary lookup: product -> entries whose keys match q or terms.

    Returns up to 3 full entries (question/answer/template).
    """
    if not lookup:
        return []
    products = lookup.get("products", {})
    entries = products.get(product, [])
    if not entries:
        return []
    qn = norm(q)
    hits = []
    for e in entries:
        keys = e.get("keys", [])
        if qn in keys:
            hits.append(e)
            continue
        if any(t in keys for t in terms):
            hits.append(e)
    return hits[:3]


def find_faq_full(faq_items, sheet, blob, terms):
    """Return full original FAQ entries matching sheet + one of terms."""
    out = []
    for item in faq_items:
        if item.get("sheet") != sheet:
            continue
        hay = norm(
            (item.get("question") or "")
            + " "
            + (item.get("answer") or "")
            + " "
            + (item.get("template") or "")
        )
        if any(t in hay for t in terms):
            out.append(item)
    return out


def load_ocr_pages():
    p = OUT_DIR / "ocr_pages.tsv"
    rows = []
    if not p.exists():
        return rows
    lines = p.read_text(encoding="utf-8").splitlines()
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append((parts[0], parts[1], parts[2]))
    return rows


def load_params_rows():
    """Load parameter fact rows: (file, page, text) from params_norm.tsv."""
    p = OUT_DIR / "params_norm.tsv"
    rows = []
    if not p.exists():
        return rows
    lines = p.read_text(encoding="utf-8").splitlines()
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append((parts[0], parts[1], "\t".join(parts[2:])))
    return rows


def load_chatgpt_rows():
    """Load ChatGPT-history rows from the WPS-synced corpus (if configured)."""
    learning = load_config().get("learning") or {}
    if not learning.get("allow_legacy_history", False):
        return []
    if not CHATGPT_CFG.exists():
        return []
    try:
        cfg = json.loads(CHATGPT_CFG.read_text(encoding="utf-8"))
    except Exception:
        return []
    corpus_dir = cfg.get("corpus_dir") or ""
    if not corpus_dir:
        return []
    p = Path(corpus_dir) / "chatgpt_norm.tsv"
    rows = []
    if not p.exists():
        return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            rows.append((parts[0], parts[1], parts[2], "\t".join(parts[3:])))
    return rows


def search_exact(rows, terms, product_filter=""):
    pn = norm(product_filter)
    hits = []
    for row in rows:
        name = row[0]
        blob = row[-1]
        page = row[1] if len(row) >= 3 else ""
        if pn and pn not in norm(name):
            continue
        # Pick the LONGEST matching term: a page containing 電源コード長 is a
        # much stronger hit than one containing only the generic コード, so
        # specificity should decide which term is reported and how it ranks.
        best = None  # (len, idx, term)
        for t in terms:
            if not t:
                continue
            idx = blob.find(t)
            if idx >= 0 and (best is None or len(t) > best[0]):
                best = (len(t), idx, t)
        if best:
            hits.append((name, page, blob, best[2], best[1]))
    return hits


def search_fuzzy(rows, terms, product_filter="", top=15):
    """RapidFuzz partial ratio over normalized rows (recall layer).

    Lazy-imports rapidfuzz so the exact-hit fast path never pays the
    ~37ms import cost.
    """
    try:
        from rapidfuzz import fuzz
    except Exception:
        return []
    pn = norm(product_filter)
    scored = []
    for row in rows:
        name = row[0]
        blob = row[-1]
        page = row[1] if len(row) >= 3 else ""
        if pn and pn not in norm(name):
            continue
        if not blob:
            continue
        best = 0.0
        best_t = ""
        for t in terms:
            if len(t) < 2:
                continue
            r = fuzz.partial_ratio(blob[:2000], t)
            if r > best:
                best = r
                best_t = t
        if best >= 62:
            scored.append((best, name, page, blob, best_t))
    scored.sort(key=lambda x: -x[0])
    return scored[:top]


def search_chatgpt_fuzzy(rows, terms, product_filter="", top=15):
    """Fuzzy search over ChatGPT-history rows (id, title, project, text)."""
    try:
        from rapidfuzz import fuzz
    except Exception:
        return []
    pn = norm(product_filter)
    scored = []
    for conv_id, title, project, text in rows:
        if pn and pn not in norm(title) and pn not in norm(text):
            continue
        if not text:
            continue
        best = 0.0
        best_t = ""
        for t in terms:
            if len(t) < 2:
                continue
            r = fuzz.partial_ratio(text[:2000], t)
            if r > best:
                best = r
                best_t = t
        if best >= 62:
            scored.append((best, conv_id, title, text[:300], best_t))
    scored.sort(key=lambda x: -x[0])
    return scored[:top]


def search_chatgpt_bm25(rows, terms, product_filter="", top=12):
    """BM25 over ChatGPT-history rows (id, title, project, text)."""
    try:
        from rank_bm25 import BM25Okapi
    except Exception:
        return []
    pn = norm(product_filter)
    corpus = []
    meta = []
    for conv_id, title, project, text in rows:
        if pn and pn not in norm(title) and pn not in norm(text):
            continue
        corpus.append(tokenize(text))
        meta.append((conv_id, title, text))
    if not corpus:
        return []
    try:
        bm = BM25Okapi(corpus)
        q = []
        for t in terms:
            q.extend(tokenize(t))
        if not q:
            return []
        scores = bm.get_scores(q)
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])
        out = []
        for i in ranked[:top]:
            if scores[i] > 0:
                out.append((scores[i], meta[i][0], meta[i][1], meta[i][2][:300]))
        return out
    except Exception:
        return []


def search_bm25(rows, terms, product_filter="", top=12):
    """BM25 ranking over the same rows (relevance layer).

    Lazy-imports rank_bm25 so the exact-hit fast path never pays the
    ~110ms import cost.
    """
    try:
        from rank_bm25 import BM25Okapi
    except Exception:
        return []
    pn = norm(product_filter)
    corpus = []
    meta = []
    for row in rows:
        name = row[0]
        blob = row[-1]
        page = row[1] if len(row) >= 3 else ""
        if pn and pn not in norm(name):
            continue
        corpus.append(tokenize(blob))
        meta.append((name, page, blob))
    if not corpus:
        return []
    try:
        bm = BM25Okapi(corpus)
        q = []
        for t in terms:
            q.extend(tokenize(t))
        if not q:
            return []
        scores = bm.get_scores(q)
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])
        out = []
        for i in ranked[:top]:
            if scores[i] > 0:
                out.append((scores[i], meta[i][0], meta[i][1], meta[i][2]))
        return out
    except Exception:
        return []


def diagnose(product: str, q: str):
    """NOT_FOUND diagnostics: which layer lost the content."""
    lines = []
    lines.append(f"DIAGNOSE product={product!r} q={q!r}")
    pn = norm(product)
    terms = query_terms(q)

    ocr_files = []
    for p in sorted(OCR_DIR.glob("*.txt")):
        if pn and pn not in norm(p.stem):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        npg = len(re.findall(r"===== PAGE (\d+) =====", text))
        ocr_files.append((p.name, npg, len(norm(text))))
    if ocr_files:
        lines.append(f"OCR_FILES ({len(ocr_files)}):")
        for name, npg, nlen in ocr_files[:10]:
            lines.append(f"  {name}: pages={npg} norm_len={nlen}")
    else:
        lines.append("OCR_FILES: none matched product")

    pdf_hits = []
    for p in SOURCE_ROOT.rglob("*.pdf"):
        if pn and pn not in norm(p.stem):
            continue
        pdf_hits.append(p)
    if pdf_hits:
        lines.append(f"PDF_FILES ({len(pdf_hits)}):")
        try:
            import pdfplumber
            for p in pdf_hits[:5]:
                with pdfplumber.open(str(p)) as pdf:
                    tl = sum(1 for pg in pdf.pages[:4] if (pg.extract_text() or "").strip())
                lines.append(f"  {p.name}: text_layer_pages={tl}/{len(pdf.pages)}")
        except Exception as e:
            lines.append(f"  pdfplumber error: {e}")
    else:
        lines.append("PDF_FILES: none matched product")

    if PAGES_DIR.exists():
        imgs = []
        for p in PAGES_DIR.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".jpg", ".png"):
                if pn and pn not in norm(p.stem):
                    continue
                imgs.append(str(p.relative_to(PAGES_DIR)))
        if imgs:
            lines.append(f"PAGE_IMAGES ({len(imgs)}):")
            for rel in imgs[:8]:
                lines.append(f"  {rel}")

    # Targeted vision candidates: page images whose OCR segment matched terms
    index_tsv = BASE / "manual_image_index" / "pages.tsv"
    if index_tsv.exists():
        cand = []
        for line in index_tsv.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) < 6:
                continue
            pdf_base, page_seq, marker, _, preview, image_rel = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
            if not image_rel:
                continue
            if pn and pn not in norm(pdf_base):
                continue
            nprev = norm(preview)
            if not any(t in nprev for t in terms if len(t) >= 2):
                continue
            cand.append((pdf_base, page_seq, image_rel))
        if cand:
            lines.append(f"CANDIDATE_IMAGES ({len(cand)}):")
            for pdf_base, page_seq, image_rel in cand[:10]:
                lines.append(f"  {pdf_base} page={page_seq} -> pdf_pages/{image_rel}")

    lines.append("NEXT_STEP: 若 OCR 为空且存在 CANDIDATE_IMAGES，建议对列出的页面图做定向识图（用户确认后执行）。")
    return "\n".join(lines)


def snippet(blob, idx, term, width=240):
    start = max(0, idx - 80)
    return blob[start : idx + len(term) + width]


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", default="")
    parser.add_argument("--q", required=True)
    parser.add_argument("--diagnose", action="store_true")
    args = parser.parse_args()

    terms = query_terms(args.q)
    lookup = load_faq_lookup()
    if args.product and lookup:
        fast_hits = lookup_faq_fast(lookup, args.product, args.q, terms)
        if fast_hits:
            print(f"HITS_LOOKUP count={len(fast_hits)}")
            for item in fast_hits:
                print("---")
                print("question:", (item.get("question") or "")[:300])
                print("answer:", item.get("answer") or "")
                print("template:", item.get("template") or "")
            if args.diagnose:
                print("\n" + diagnose(args.product, args.q))
            return 0

    faq_rows = load_rows("faq")
    faq_full = load_faq_full()
    kdocs_rows = load_rows("kdocs")
    spec_rows = load_rows("spec")
    ocr_pages = load_ocr_pages()
    params_rows = load_params_rows()
    approved_rows = load_rows("approved_cases")
    chatgpt_rows = load_chatgpt_rows()

    results = []

    # FAQ (exact path)
    for name, page, blob, t, idx in search_exact(faq_rows, terms, args.product):
        full_items = find_faq_full(faq_full, name, blob, terms)
        if full_items:
            for item in full_items[:3]:
                results.append((1000.0, "FAQ", name, page, json.dumps(item, ensure_ascii=False), t))
        else:
            results.append((1000.0, "FAQ", name, page, snippet(blob, idx, t), t))

    # KDOCS
    for name, page, blob, t, idx in search_exact(kdocs_rows, terms, args.product):
        results.append((900.0, "KDOCS", name, page, snippet(blob, idx, t), t))

    # SPEC
    for name, page, blob, t, idx in search_exact(spec_rows, terms, args.product):
        results.append((950.0, "SPEC", name, page, snippet(blob, idx, t), t))

    # OCR pages
    for name, page, blob, t, idx in search_exact(ocr_pages, terms, args.product):
        results.append((980.0, "OCR", name, page, snippet(blob, idx, t), t))

    # PARAMS (parameter fact layer)
    for name, page, blob, t, idx in search_exact(params_rows, terms, args.product):
        results.append((975.0, "PARAMS", name, page, snippet(blob, idx, t), t))

    # Only explicitly approved customer-service cases enter this layer.
    for name, page, blob, t, idx in search_exact(approved_rows, terms, args.product):
        results.append((965.0, "APPROVED", name, page, snippet(blob, idx, t), t))

    # CHATGPT history layer: historical successful handling records.
    for row in chatgpt_rows:
        conv_id, title, project, text = row
        pn = norm(args.product)
        if pn and pn not in norm(title) and pn not in norm(text):
            continue
        best = None
        for t in terms:
            if not t:
                continue
            idx = text.find(t)
            if idx >= 0 and (best is None or len(t) > best[0]):
                best = (len(t), idx, t)
        if best:
            idx = best[1]
            results.append((920.0, "CHATGPT", title, project, snippet(text, idx, best[2]), best[2]))

    # Exact hits exist -> return immediately (fast path, no fuzzy/bm25).
    if results:
        results.sort(key=lambda x: (-(len(x[5]) if x[5] else 0), -x[0]))
        seen = set()
        uniq = []
        for r in results:
            key = (r[1], r[2], r[3])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(r)
        print(f"HITS ranked={len(uniq)} terms={','.join(terms)}")
        for score, layer, name, page, snip, term in uniq[:5]:
            loc = f" page={page}" if page else ""
            print("---")
            print(f"[{score:.1f}] {layer} | {name}{loc} | term={term or '-'}")
            if layer == "FAQ":
                try:
                    item = json.loads(snip)
                    print("  question:", item.get("question", "")[:300])
                    print("  answer:", item.get("answer", ""))
                    print("  template:", item.get("template", ""))
                    continue
                except Exception:
                    pass
            print(f"  {snip[:1500]}")
        if args.diagnose:
            print("\n" + diagnose(args.product, args.q))
        return 0

    # No exact hit -> fall back to fuzzy + BM25 for recall.
    for score, name, page, blob, t in search_fuzzy(faq_rows, terms, args.product):
        results.append((score, "FAQ", name, page, blob[:300], t))
    for score, name, page, blob in search_bm25(faq_rows, terms, args.product):
        results.append((score, "FAQ", name, page, blob[:300], ""))
    for score, name, page, blob, t in search_fuzzy(kdocs_rows, terms, args.product):
        results.append((score, "KDOCS", name, page, blob[:300], t))
    for score, name, page, blob in search_bm25(kdocs_rows, terms, args.product):
        results.append((score, "KDOCS", name, page, blob[:300], ""))
    for score, name, page, blob, t in search_fuzzy(spec_rows, terms, args.product):
        results.append((score, "SPEC", name, page, blob[:300], t))
    for score, name, page, blob in search_bm25(spec_rows, terms, args.product):
        results.append((score, "SPEC", name, page, blob[:300], ""))
    for score, name, page, blob, t in search_fuzzy(ocr_pages, terms, args.product):
        results.append((score * 0.95, "OCR", name, page, blob[:300], t))
    for score, name, page, blob in search_bm25(ocr_pages, terms, args.product):
        results.append((score, "OCR", name, page, blob[:300], ""))
    for score, name, page, blob, t in search_fuzzy(params_rows, terms, args.product):
        results.append((score * 0.95, "PARAMS", name, page, blob[:300], t))
    for score, name, page, blob in search_bm25(params_rows, terms, args.product):
        results.append((score, "PARAMS", name, page, blob[:300], ""))
    for score, name, page, blob, t in search_fuzzy(approved_rows, terms, args.product):
        results.append((score * 0.95, "APPROVED", name, page, blob[:300], t))
    for score, name, page, blob in search_bm25(approved_rows, terms, args.product):
        results.append((score, "APPROVED", name, page, blob[:300], ""))
    for score, name, page, blob, t in search_chatgpt_fuzzy(chatgpt_rows, terms, args.product):
        results.append((score * 0.90, "CHATGPT", name, page, blob, t))
    for score, name, page, blob in search_chatgpt_bm25(chatgpt_rows, terms, args.product):
        results.append((score, "CHATGPT", name, page, blob, ""))

    seen = set()
    uniq = []
    for r in sorted(results, key=lambda x: (-(len(x[5]) if x[5] else 0), -x[0])):
        key = (r[1], r[2], r[3])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)

    if not uniq:
        print("NOT_FOUND")
        if args.diagnose:
            print(diagnose(args.product, args.q))
        return 1

    print(f"HITS ranked={len(uniq)} terms={','.join(terms)}")
    for score, layer, name, page, snip, term in uniq[:15]:
        loc = f" page={page}" if page else ""
        print("---")
        print(f"[{score:.1f}] {layer} | {name}{loc} | term={term or '-'}")
        print(f"  {snip[:400]}")
    if args.diagnose:
        print("\n" + diagnose(args.product, args.q))
    return 0


if __name__ == "__main__":
    sys.exit(main())
