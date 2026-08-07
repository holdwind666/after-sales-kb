"""Build a page-grained normalized search index for the after-sales KB.

Key changes vs the old whole-file index:
  1. OCR text is indexed PER PAGE (one row per page), so hits can report
     the exact page number instead of just the manual name.
  2. A zh/ja synonym dictionary is written to quick_index/synonyms.tsv so
     query-side expansion is data-driven and maintainable.
  3. FAQ/kdocs/spec stay normalized (space-removed, lowercase).

Outputs (under <cache>/quick_index/):
  - faq_norm.tsv    : sheet \t normalized question+answer+template
  - faq_full.jsonl  : sheet, question, answer, template (ORIGINAL text, one JSON per line)
  - ocr_pages.tsv   : file_context \t page_seq \t normalized page text
  - ocr_sources.tsv : file \t ocr_pages \t normalized_len   (diagnostic layer)
  - kdocs_norm.tsv  : file \t normalized full text
  - spec_norm.tsv   : file \t normalized text
  - synonyms.tsv    : zh_term \t ja_term1 \t ja_term2 ...
  - meta.json       : build time + counts

Usage:
  python build_quick_index.py
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"E:\说明书与视频（第9台）\_售后模板缓存")
SOURCE_ROOT = BASE.parent
FAQ_DIR = BASE / "faq"
OCR_DIR = BASE / "pdf_ocr"
KDOCS_DIR = BASE / "kdocs"
REPAIR_OVERLAY = BASE / "ocr_repair" / "overlay.tsv"
OUT_DIR = BASE / "quick_index"

PAGE_SPLIT_RE = re.compile(r"===== PAGE (\d+) =====")

DEFAULT_SYNONYMS = {
    "包装内容": ["セット内容", "同梱物", "同梱", "内容品", "パッケージ内容", "付属品"],
    "包装清单": ["セット内容", "同梱物", "内容品", "パッケージ内容"],
    "箱子里有什么": ["セット内容", "同梱物", "内容品", "付属品"],
    "配件": ["付属品", "同梱", "同梱物", "附属", "付属", "パーツ", "補修用キット", "セット内容"],
    "附件": ["付属品", "同梱", "附属", "付属", "パーツ", "セット内容"],
    "零件": ["付属品", "パーツ", "部品"],
    "线长": ["線長", "コード長", "ケーブル長", "電源コード", "充電ケーブル"],
    "线长度": ["線長", "コード長", "ケーブル長", "電源コード", "充電ケーブル"],
    "电线多长": ["線長", "コード長", "ケーブル長", "電源コード"],
    "充电": ["充電", "チャージ"],
    "不加热": ["无法加热", "加熱しない", "温まらない", "発熱しない", "加熱不能"],
    "无法加热": ["加熱しない", "温まらない", "発熱しない", "加熱不能"],
    "不能充电": ["无法充电", "充電できない", "充電不能"],
    "不充电": ["无法充电", "充電できない"],
    "充不上电": ["无法充电", "充電できない"],
    "断电": ["自动关机", "自动停止", "停止工作", "过载", "過負荷", "電源が切れる"],
    "自动关机": ["自动停止", "停止工作", "过载", "過負荷"],
    "不出激光": ["不出光", "不发光", "フラッシュが出ない", "照射できない", "発光しない"],
    "不出光": ["フラッシュが出ない", "照射できない", "発光しない"],
    "不出泡沫": ["不出泡", "出泡异常", "泡が出ない"],
    "出泡异常": ["不出泡", "泡が出ない"],
    "不喷": ["不出泡沫", "不出泡", "噴霧しない"],
    "漏水": ["水漏れ", "漏れ"],
    "噪音": ["异音", "異音", "音が大きい"],
    "声音大": ["噪音", "异音", "異音"],
    "吸力小": ["吸力弱", "灰尘吸不进", "吸引力が弱い"],
    "吸不进": ["灰尘吸不进", "吸引力が弱い", "吸い込まない"],
    "堵塞": ["詰まり", "堵"],
    "不启动": ["无法启动", "启动异常", "起動しない"],
    "启动不了": ["无法启动", "启动异常", "起動しない"],
    "不转": ["不工作", "不运转", "无法启动", "起動しない", "動かない", "稼働できない", "不转动"],
    "不转动": ["不工作", "不运转", "无法启动", "起動しない", "動かない", "稼働できない"],
    "不运转": ["不工作", "无法启动", "起動しない", "動かない", "稼働できない"],
    "不工作": ["无法启动", "不运转", "起動しない", "動かない", "稼働できない"],
    "不动": ["不工作", "不运转", "无法启动", "起動しない", "動かない", "稼働できない"],
    "不能开机": ["无法启动", "启动异常", "起動しない", "電源が入らない"],
    "不开机": ["无法启动", "启动异常", "起動しない", "電源が入らない"],
    "不出雾": ["噴霧しない", "雾化"],
    # 参数类：线长/电源线/尺寸/功率/电压/容量/重量（支持查询时按短语扩展）
    "线长": ["線長", "コード長", "ケーブル長", "電源コード長", "電源側コード長", "本体側コード長"],
    "线长度": ["線長", "コード長", "ケーブル長", "電源コード長", "電源側コード長", "本体側コード長"],
    "电线多长": ["線長", "コード長", "ケーブル長", "電源コード長", "電源側コード長", "本体側コード長"],
    "电源线": ["電源コード", "電源側コード", "コード"],
    "电源线长度": ["電源コード長", "電源側コード長", "本体側コード長", "電源側", "本体側"],
    "充电线": ["充電ケーブル", "充電コード", "USBケーブル"],
    "尺寸": ["寸法", "サイズ", "外形寸法"],
    "功率": ["消費電力", "定格出力", "定格消費電力"],
    "消费电力": ["消費電力", "定格消費電力"],
    "消費電力": ["消费电力", "功率"],
    "电压": ["定格電圧", "電圧", "入力電圧"],
    "容量": ["容量", "タンク容量"],
    "重量": ["重量", "質量"],
}


def norm(s: str) -> str:
    """Remove ALL whitespace and lowercase (CJK unaffected)."""
    return re.sub(r"\s+", "", s or "").lower()


def load_ocr_path_map():
    """Map OCR basename -> directory context (from manual_image_index pages)."""
    pages_tsv = BASE / "manual_image_index" / "pages.tsv"
    mapping = {}
    if not pages_tsv.exists():
        return mapping
    for line in pages_tsv.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        pdf_base = parts[0].strip()
        rel = parts[5].strip()
        if not rel:
            continue
        norm_rel = rel.replace("/", "\\")
        idx = norm_rel.rfind("\\")
        if idx < 0:
            mapping.setdefault(pdf_base, pdf_base)
            continue
        mapping.setdefault(pdf_base, norm_rel[:idx] + "\\" + pdf_base)
    return mapping


def split_ocr_pages(text: str):
    """Split OCR text into (page_seq, page_text) pairs.

    Supports '===== PAGE N =====' markers; content before the first marker
    belongs to page 1.
    """
    matches = list(PAGE_SPLIT_RE.finditer(text))
    if not matches:
        return [(1, text)]
    pages = []
    pre = text[: matches[0].start()].strip()
    if pre:
        pages.append((1, pre))
    for i, m in enumerate(matches):
        seq = int(m.group(1))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end].strip()
        pages.append((seq, body))
    if not pages:
        pages = [(1, text)]
    return pages


def iter_spec_files():
    """Yield spec-like xlsx/pdf files under source 说明书 dir (read-only)."""
    spec_dirs = ("规格书", "规格", "spec", "Spec")
    for d in SOURCE_ROOT.glob("说明书/*"):
        if not d.is_dir():
            continue
        for sub in d.rglob("*"):
            if not sub.is_file() or sub.suffix.lower() not in (".xlsx", ".pdf"):
                continue
            if any(k in sub.parent.name for k in spec_dirs):
                yield sub


def extract_xlsx_text(path: Path) -> str:
    try:
        import openpyxl
    except Exception:
        return ""
    parts = []
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                vals = [str(v).strip() for v in row if v is not None and str(v).strip()]
                if vals:
                    parts.append(" ".join(vals))
        wb.close()
    except Exception:
        return ""
    return "\n".join(parts)


def extract_pdf_text(path: Path) -> str:
    """Extract embedded text layer from a spec PDF (empty when scanned)."""
    try:
        import pdfplumber
    except Exception:
        return ""
    parts = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for p in pdf.pages:
                t = (p.extract_text() or "").strip()
                if t:
                    parts.append(t)
    except Exception:
        return ""
    return "\n".join(parts)


PARAM_HINT_RE = re.compile(
    r"(長|長さ|コード|線|線長|寸法|サイズ|定格|消費電力|容量|重量|質量|出力|電圧|"
    r"线长|电源线|电线|尺寸|功率|电压|容量|重量|配件|付属品|セット内容|電源側|本体側|充電ケーブル)"
)

# Human-verified parameter facts. WinRT OCR is unreliable on small technical
# table cells (it read 18m instead of 1.8M on one spec sheet), so verified
# values live in a seed table that is merged into the PARAMS layer. The
# source PDF/page makes the fact traceable. Users can extend
# quick_index/param_seeds.tsv (same columns, tab-separated) and rebuild.
DEFAULT_PARAM_SEEDS = [
    {
        "product": "电热毯（肖玲）",
        "model": "MZM-5526",
        "attribute": "電源コード長",
        "value": "電源側 1.8m / 本体側 0.6m",
        "source": "说明书\\肖玲\\电热毯\\规格书\\单人产品规格书-MZM-5526-星盟版.pdf",
        "page": "4",
    },
    {
        "product": "电热毯（肖玲）",
        "model": "MZM-8026",
        "attribute": "電源コード長",
        "value": "電源側 1.8m / 本体側 1.2m",
        "source": "说明书\\肖玲\\电热毯\\规格书\\双人产品规格书-MZM-8026-星盟版.pdf",
        "page": "4",
    },
]

PARAM_SEED_COLUMNS = ["product", "model", "attribute", "value", "source", "page"]


def extract_param_rows(text: str, max_rows: int = 400):
    """Keep only lines that look like parameter facts (length/code/size/...)."""
    out = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if PARAM_HINT_RE.search(line):
            nl = norm(line)
            if nl and nl not in out:
                out.append(nl)
        if len(out) >= max_rows:
            break
    return out


def write_param_seeds_file():
    """Write the default seed table once (user-extendable afterwards)."""
    p = OUT_DIR / "param_seeds.tsv"
    if p.exists():
        return
    with p.open("w", encoding="utf-8", newline="") as f:
        f.write("\t".join(PARAM_SEED_COLUMNS) + "\n")
        for s in DEFAULT_PARAM_SEEDS:
            f.write(
                "\t".join(str(s.get(c, "")) for c in PARAM_SEED_COLUMNS) + "\n"
            )


def load_param_seeds() -> list[dict]:
    write_param_seeds_file()
    p = OUT_DIR / "param_seeds.tsv"
    rows = []
    if not p.exists():
        return rows
    lines = p.read_text(encoding="utf-8").splitlines()
    if not lines:
        return rows
    header = lines[0].split("\t")
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < len(header):
            continue
        row = dict(zip(header, parts))
        if row.get("value", "").strip():
            rows.append(row)
    return rows


def load_repair_overlay() -> dict[tuple[str, str], str]:
    """Load vision-repaired page text (ocr_repair/overlay.tsv).

    Keys are (pdf_base, page_seq). build_quick_index merges these pages
    over the WinRT OCR text so weak spec-table values become searchable.
    """
    overlay = {}
    if not REPAIR_OVERLAY.exists():
        return overlay
    for line in REPAIR_OVERLAY.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        base, seq, text = parts[0], parts[1], parts[2]
        if not base or not seq:
            continue
        try:
            text = json.loads(text)
        except Exception:
            pass
        overlay[(base, seq)] = text
    return overlay


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    counts = {"faq": 0, "ocr_pages": 0, "kdocs": 0, "spec": 0, "params": 0, "seeds": 0}
    ocr_path_map = load_ocr_path_map()
    repair_overlay = load_repair_overlay()

    # FAQ index
    with (OUT_DIR / "faq_norm.tsv").open("w", encoding="utf-8", newline="") as f:
        with (OUT_DIR / "faq_full.jsonl").open("w", encoding="utf-8", newline="") as full_f:
            for p in sorted(FAQ_DIR.glob("*.json")):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                sheet = data.get("sheet", p.stem)
                for item in data.get("items", []):
                    blob = norm(
                        (item.get("question") or "")
                        + " "
                        + (item.get("answer") or "")
                        + " "
                        + (item.get("template") or "")
                    )
                    f.write(f"{sheet}\t{blob}\n")
                    full_f.write(
                        json.dumps(
                            {
                                "sheet": sheet,
                                "question": item.get("question") or "",
                                "answer": item.get("answer") or "",
                                "template": item.get("template") or "",
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    counts["faq"] += 1

    # OCR per-page index + source diagnostics
    with (OUT_DIR / "ocr_pages.tsv").open("w", encoding="utf-8", newline="") as f:
        f.write("file\tpage_seq\tpage_text\n")
        with (OUT_DIR / "ocr_sources.tsv").open("w", encoding="utf-8", newline="") as src_f:
            src_f.write("file\tocr_pages\tnormalized_len\n")
            for p in sorted(OCR_DIR.glob("*.txt")):
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    text = ""
                pages = split_ocr_pages(text)
                name = ocr_path_map.get(p.stem, p.name)
                src_f.write(f"{name}\t{len(pages)}\t{len(norm(text))}\n")
                for seq, body in pages:
                    repaired = repair_overlay.get((p.stem, str(seq)))
                    if repaired is not None:
                        body = repaired + "\n" + body
                    f.write(f"{name}\t{seq}\t{norm(body)}\n")
                    counts["ocr_pages"] += 1

    # kdocs index
    with (OUT_DIR / "kdocs_norm.tsv").open("w", encoding="utf-8", newline="") as f:
        for p in sorted(KDOCS_DIR.glob("*.txt")):
            if p.name == "_capture_log.txt":
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            f.write(f"{p.name}\t{norm(text)}\n")
            counts["kdocs"] += 1

    # spec files (xlsx text + pdf embedded text layer)
    with (OUT_DIR / "spec_norm.tsv").open("w", encoding="utf-8", newline="") as f:
        for p in sorted(iter_spec_files(), key=lambda x: str(x)):
            if p.suffix.lower() == ".xlsx":
                text = extract_xlsx_text(p)
            else:
                text = extract_pdf_text(p)
            if not text.strip():
                continue
            rel = str(p.relative_to(SOURCE_ROOT))
            f.write(f"{rel}\t{norm(text)}\n")
            counts["spec"] += 1

    # parameter fact layer: OCR pages + spec texts, only lines with param hints
    with (OUT_DIR / "params_norm.tsv").open("w", encoding="utf-8", newline="") as f:
        f.write("file\tpage\tparam_text\n")
        for p in sorted(OCR_DIR.glob("*.txt")):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = ""
            name = ocr_path_map.get(p.stem, p.name)
            for seq, body in split_ocr_pages(text):
                repaired = repair_overlay.get((p.stem, str(seq)))
                if repaired is not None:
                    body = repaired + "\n" + body
                rows = extract_param_rows(body)
                if rows:
                    f.write(f"{name}\t{seq}\t{' '.join(rows)}\n")
                    counts["params"] += 1
        for p in sorted(iter_spec_files(), key=lambda x: str(x)):
            if p.suffix.lower() == ".xlsx":
                text = extract_xlsx_text(p)
            else:
                text = extract_pdf_text(p)
            if not text.strip():
                continue
            rows = extract_param_rows(text)
            if rows:
                rel = str(p.relative_to(SOURCE_ROOT))
                f.write(f"{rel}\t\t{' '.join(rows)}\n")
                counts["params"] += 1
        for seed in load_param_seeds():
            fact = " ".join(
                [seed.get("model", ""), seed.get("attribute", ""), seed.get("value", "")]
            ).strip()
            if not fact:
                continue
            f.write(
                f"param_seeds:{seed.get('product', '')}\t{seed.get('page', '')}\t{norm(fact)}\n"
            )
            counts["params"] += 1
            counts["seeds"] += 1

    # synonym dictionary
    with (OUT_DIR / "synonyms.tsv").open("w", encoding="utf-8", newline="") as f:
        for zh, ja_list in DEFAULT_SYNONYMS.items():
            f.write(zh + "\t" + "\t".join(ja_list) + "\n")

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": counts,
    }
    (OUT_DIR / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
