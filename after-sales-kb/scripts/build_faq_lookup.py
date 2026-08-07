"""Precompile FAQ templates into a product -> keyword -> full-reply lookup.

Purpose: daily queries hit a plain dictionary lookup (fast path) instead of
scanning all index rows; full question/answer/template is returned in one
call. Runs in ~1-2s during the first full build (no OCR/vision/network).

Output (under <cache>/quick_index/):
  - faq_lookup.json : {
      "_meta": {generated_at, entry_count},
      "products": {
        "<sheet>": [
          {"keys": [...], "question": "...", "answer": "...", "template": "..."}
        ]
      }
    }

Key generation:
  - normalized full question
  - synonyms.tsv zh terms whose ja/zh expansion appears anywhere in the entry
  - common service words (配件/包装内容/不转/不工作/... ) that appear in the
    entry text, so customer wording maps directly to the right template.

Usage:
  python build_faq_lookup.py
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"E:\说明书与视频（第9台）\_售后模板缓存")
FAQ_DIR = BASE / "faq"
OUT_DIR = BASE / "quick_index"
OUT_FILE = OUT_DIR / "faq_lookup.json"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def load_synonyms():
    p = OUT_DIR / "synonyms.tsv"
    syn = {}
    if not p.exists():
        return syn
    for line in p.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            syn[parts[0]] = parts[1:]
    return syn


def entry_keys(question, answer, template, synonyms):
    """Build the lookup keys for one FAQ entry."""
    blob = question + " " + answer + " " + template
    nblob = norm(blob)
    keys = set()
    qn = norm(question)
    if qn:
        keys.add(qn)
    # any synonym zh term whose expansion appears in the entry text
    for zh, ja_list in synonyms.items():
        if norm(zh) in nblob:
            keys.add(norm(zh))
            continue
        for ja in ja_list:
            if norm(ja) in nblob:
                keys.add(norm(zh))
                break
    return sorted(k for k in keys if k)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    synonyms = load_synonyms()
    products = {}
    total = 0
    for p in sorted(FAQ_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        sheet = data.get("sheet", p.stem)
        entries = []
        for item in data.get("items", []):
            q = (item.get("question") or "").strip()
            a = (item.get("answer") or "").strip()
            t = (item.get("template") or "").strip()
            if not (q or a or t):
                continue
            keys = entry_keys(q, a, t, synonyms)
            entries.append(
                {
                    "keys": keys,
                    "question": q,
                    "answer": a,
                    "template": t,
                }
            )
            total += 1
        if entries:
            products[sheet] = entries

    payload = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "entry_count": total,
            "product_count": len(products),
        },
        "products": products,
    }
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload["_meta"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
