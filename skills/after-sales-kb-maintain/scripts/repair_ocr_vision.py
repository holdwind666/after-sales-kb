"""Repair weak/broken OCR pages with vision (automated, no user prompts).

Pipeline (all commands are script-internal; the user only runs one step):
  plan  -> scan OCR pages for weak/empty/spec-like pages, write
           ocr_repair/todo.tsv
  run   -> call vision-skill for every todo page (fixed internal prompt),
           append results to ocr_repair/repairs.tsv
  merge -> merge ok repairs into ocr_repair/overlay.tsv; build_quick_index
           consumes this overlay automatically
  all   -> plan + run + merge

Machines with a multimodal model: run `plan`, let the model read the listed
page images itself and append rows to repairs.tsv (same columns), then run
`merge`. No complicated user prompt is needed in either mode.

Usage:
  python repair_ocr_vision.py plan [--filter 电热毯] [--force-spec]
  python repair_ocr_vision.py run [--workers 2] [--limit N] [--force]
  python repair_ocr_vision.py merge
  python repair_ocr_vision.py all [--workers 2] [--limit N]
"""

import argparse
import concurrent.futures
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from kb_paths import cache_root

BASE = cache_root()
OCR_DIR = BASE / "pdf_ocr"
PAGES_DIR = BASE / "pdf_pages"
INDEX_TSV = BASE / "manual_image_index" / "pages.tsv"
OUT_DIR = BASE / "ocr_repair"

NODE = Path(os.environ.get("KB_NODE") or shutil.which("node") or str(Path.home() / ".missing-node"))
_vision_candidates = [
    Path.home() / ".codex" / "skills" / "vision-skill" / "scripts" / "vision.js",
    Path.home() / ".agents" / "skills" / "vision-skill" / "scripts" / "vision.js",
]
VISION_SCRIPT = Path(os.environ.get("KB_VISION_SCRIPT") or next((str(p) for p in _vision_candidates if p.exists()), str(Path.home() / ".missing-vision-skill")))

# Fixed internal prompt: verbatim text extraction, no summarization.
REPAIR_PROMPT = (
    "请逐字原样读出这张页面上的所有文字和数值，包括表格标签、型号、规格、"
    "参数名称、数字和单位（例如 W/V/Hz/cm/m/kg/ml/時間）。"
    "不要概括，不要翻译，不要补充说明，按页面顺序一行一行输出原文。"
)

PAGE_SPLIT_RE = re.compile(r"===== PAGE (\d+) =====")

# OCR pages are considered weak when they look like spec pages but no
# parameter label survived, or when the normalized text is nearly empty.
SPEC_WORDS = ("仕様", "規格", "spec", "制品仕様", "产品规格", "规格")
PARAM_LABELS = (
    "消費電力", "定格消費電力", "定格電圧", "定格周波数", "定格",
    "製品寸法", "寸法", "コード長", "電源コード", "容量", "重量", "材質",
    "出力", "電圧", "タイマー", "温度調節", "消費电力", "功率", "电压",
    "尺寸", "容量", "重量", "线长",
)
VALUE_RE = re.compile(r"\d+\s*(W|V|Hz|cm|CM|m|kg|g|ml|本|時間|H)\b")

_write_lock = threading.Lock()


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def split_ocr_pages(text: str):
    """Same page splitting semantics as build_quick_index."""
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


def read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def page_weak(reason_ctx: str, body: str, force_spec: bool) -> str:
    """Return a reason string when the page needs vision repair, else ''."""
    n = norm(body)
    nlen = len(n)
    if nlen < 30:
        return f"empty_ocr len={nlen}"
    has_spec = any(w in n for w in SPEC_WORDS)
    has_label = any(w in n for w in PARAM_LABELS)
    has_value = bool(VALUE_RE.search(body))
    # A genuine spec table page: 仕様/規格 together with 品名/製品型番/品番.
    # This avoids flagging covers/TOCs/safety pages that merely contain the
    # word 仕様 (e.g. 予告なく仕様変更される場合).
    spec_table = has_spec and ("製品型番" in n or "品番" in n or "品名" in n)
    if spec_table and not has_value:
        return "spec_table_missing_values"
    if force_spec and (spec_table or (has_spec and has_label)) and not has_value:
        return "spec_page_no_values"
    if ("规格" in reason_ctx or "仕様" in reason_ctx or "spec" in reason_ctx.lower()) and not has_value:
        return "spec_file_page_no_values"
    return ""


def build_todo(filter_substr: str = "", force_spec: bool = False, min_len: int = 0):
    """Scan OCR + page-image index and write ocr_repair/todo.tsv."""
    if not INDEX_TSV.exists():
        print(f"INDEX_MISSING {INDEX_TSV}")
        return 1
    # page image rows keyed by (pdf_base, page_seq)
    images = {}
    for line in INDEX_TSV.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        pdf_base, page_seq, _, _, _, image_rel = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
        if not image_rel:
            continue
        images[(pdf_base, page_seq)] = image_rel

    rows = []
    for p in sorted(OCR_DIR.glob("*.txt")):
        base = p.stem
        if filter_substr and norm(filter_substr) not in norm(base):
            continue
        text = read_utf8(p)
        for seq, body in split_ocr_pages(text):
            image_rel = images.get((base, str(seq)))
            if not image_rel:
                continue
            reason = page_weak(base, body, force_spec)
            if reason.startswith("empty_ocr"):
                try:
                    n = int(re.search(r"len=(\d+)", reason).group(1))
                    if n < min_len:
                        continue
                except Exception:
                    pass
            if reason:
                rows.append([base, str(seq), image_rel, reason, body[:120].replace("\t", " ").replace("\n", " ")])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "todo.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["pdf_base", "page_seq", "image_rel", "reason", "ocr_preview"])
        w.writerows(rows)
    print(f"TODO_PAGES={len(rows)} -> {OUT_DIR / 'todo.tsv'}")
    return 0


def load_tsv_rows(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def vision_describe(image_path: Path, retries: int = 2) -> str:
    if not VISION_SCRIPT.exists():
        raise FileNotFoundError(
            "vision-skill not installed; on a multimodal model machine, "
            "read the todo page images directly and append rows to "
            "ocr_repair/repairs.tsv, then run merge."
        )
    if not NODE.exists():
        raise FileNotFoundError(f"node not found: {NODE}")
    cmd = [str(NODE), str(VISION_SCRIPT), str(image_path), REPAIR_PROMPT]
    last_err = ""
    for attempt in range(retries + 1):
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", timeout=240
            )
            if proc.returncode == 0:
                out = proc.stdout.strip()
                if out:
                    return out
                last_err = "empty vision output"
            else:
                last_err = (proc.stderr or proc.stdout or "").strip()[:500]
        except subprocess.TimeoutExpired:
            last_err = "timeout"
        except Exception as e:
            last_err = str(e)[:500]
        if attempt < retries:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(last_err or "vision call failed")


def run_repairs(workers: int = 2, limit: int = 0, force: bool = False, include_empty: bool = False) -> int:
    todo = load_tsv_rows(OUT_DIR / "todo.tsv")
    if not todo:
        print("TODO_EMPTY run plan first")
        return 1
    if not include_empty:
        todo = [r for r in todo if not (r.get("reason") or "").startswith("empty_ocr")]
    repairs_path = OUT_DIR / "repairs.tsv"
    done = set()
    if repairs_path.exists() and not force:
        for r in load_tsv_rows(repairs_path):
            if (r.get("status") or "").startswith("ok"):
                done.add((r.get("pdf_base", ""), r.get("page_seq", "")))
    pending = [r for r in todo if (r.get("pdf_base", ""), r.get("page_seq", "")) not in done]
    if limit > 0:
        pending = pending[:limit]
    if not pending:
        print("NOTHING_TO_REPAIR")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = fail = 0

    def process(row):
        nonlocal ok, fail
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        base = row["pdf_base"]
        seq = row["page_seq"]
        rel = row["image_rel"]
        img = PAGES_DIR / rel
        if not img.exists():
            return [base, seq, rel, "", "", f"fail:missing-image:{rel}", now]
        try:
            text = vision_describe(img)
            return [base, seq, rel, json.dumps(text, ensure_ascii=False), "vision-skill/qwen", "ok", now]
        except Exception as e:
            return [base, seq, rel, "", "", f"fail:{str(e)[:200]}", now]

    with repairs_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        if repairs_path.stat().st_size == 0:
            w.writerow(["pdf_base", "page_seq", "image_rel", "text", "model", "status", "generated_at"])
        if workers <= 1:
            for i, row in enumerate(pending, 1):
                r = process(row)
                with _write_lock:
                    w.writerow(r)
                    if r[5] == "ok":
                        ok += 1
                    else:
                        fail += 1
                        print(f"  FAIL {r[0]} page={r[1]}: {r[5]}")
                if i % 5 == 0 or i == len(pending):
                    print(f"  progress {i}/{len(pending)} ok={ok} fail={fail}")
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                futures = {ex.submit(process, row): row for row in pending}
                done_count = 0
                for fut in concurrent.futures.as_completed(futures):
                    r = fut.result()
                    with _write_lock:
                        w.writerow(r)
                        f.flush()
                        if r[5] == "ok":
                            ok += 1
                        else:
                            fail += 1
                            print(f"  FAIL {r[0]} page={r[1]}: {r[5]}")
                    done_count += 1
                    if done_count % 10 == 0 or done_count == len(pending):
                        print(f"  progress {done_count}/{len(pending)} ok={ok} fail={fail}")
    print(f"REPAIR_DONE ok={ok} fail={fail} -> {repairs_path}")
    return 0


def merge_repairs() -> int:
    repairs = load_tsv_rows(OUT_DIR / "repairs.tsv")
    ok_rows = [r for r in repairs if (r.get("status") or "") == "ok"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "overlay.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["pdf_base", "page_seq", "text"])
        for r in ok_rows:
            try:
                text = json.loads(r.get("text") or '""')
            except Exception:
                text = r.get("text") or ""
            w.writerow([r["pdf_base"], r["page_seq"], json.dumps(text, ensure_ascii=False)])
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repaired_pages": len(ok_rows),
        "failed": sum(1 for r in repairs if (r.get("status") or "").startswith("fail")),
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"MERGED_PAGES={len(ok_rows)} -> {OUT_DIR / 'overlay.tsv'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--filter", default="")
    p_plan.add_argument("--force-spec", action="store_true")
    p_plan.add_argument("--min-len", type=int, default=0,
                        help="skip empty_ocr pages whose normalized length is below this value")
    p_run = sub.add_parser("run")
    p_run.add_argument("--workers", type=int, default=2)
    p_run.add_argument("--limit", type=int, default=0)
    p_run.add_argument("--force", action="store_true")
    p_run.add_argument("--include-empty", action="store_true",
                       help="also repair empty_ocr pages (can be hundreds; costly)")
    p_merge = sub.add_parser("merge")
    p_all = sub.add_parser("all")
    p_all.add_argument("--filter", default="")
    p_all.add_argument("--force-spec", action="store_true")
    p_all.add_argument("--min-len", type=int, default=0)
    p_all.add_argument("--workers", type=int, default=2)
    p_all.add_argument("--limit", type=int, default=0)
    p_all.add_argument("--include-empty", action="store_true")
    args = parser.parse_args()

    if args.cmd == "plan":
        return build_todo(args.filter, args.force_spec, args.min_len)
    if args.cmd == "run":
        return run_repairs(args.workers, args.limit, args.force, args.include_empty)
    if args.cmd == "merge":
        return merge_repairs()
    if args.cmd == "all":
        rc = build_todo(args.filter, args.force_spec, args.min_len)
        if rc:
            return rc
        rc = run_repairs(args.workers, args.limit, False, args.include_empty)
        if rc:
            return rc
        return merge_repairs()
    return 1


if __name__ == "__main__":
    sys.exit(main())
