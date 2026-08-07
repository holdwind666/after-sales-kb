"""Build a semantic (vision) index for manual page images and xlsx media images.

The script prefers the current Codex model for image understanding. When the
current model has no multimodal vision (the typical case on this machine),
it falls back to the vision-skill (qwen via OpenAI-compatible API). If
vision-skill is not installed, it prints a clear install hint and skips.

Outputs (all under <cache>/vision_index/):
  - images.tsv            : merged index (source | image_rel | description | model | status | generated_at)
  - shard_<name>.tsv      : per-shard output (parallel runs)
  - summary.json          : merged counts
  - summary_<name>.json   : per-shard counts

Usage:
  python build_vision_index.py [--source manual|xlsx|all] [--filter <substr>]
                               [--limit N] [--force] [--workers N]
                               [--split N] [--split-index I] [--shard NAME]
                               [--status] [--merge]

Examples:
  # Index the first S1 manual pages only (verification)
  python build_vision_index.py --source manual --filter "S1 脱毛仪说明书" --limit 2

  # Parallel sharded run (4 runners x 2 workers = 8 concurrent vision calls)
  python build_vision_index.py --source all --split 4 --split-index 0 --workers 2 --shard p0
  python build_vision_index.py --source all --split 4 --split-index 1 --workers 2 --shard p1

  # Check how many images remain in a shard (without processing)
  python build_vision_index.py --source all --split 4 --split-index 0 --shard p0 --status

  # Merge all shard files into images.tsv after shards finish
  python build_vision_index.py --merge
"""

import argparse
import concurrent.futures
import csv
import json
import os
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(os.environ.get("KB_CACHE_BASE", r"E:\说明书与视频（第9台）\_售后模板缓存"))
MANUAL_PAGES = BASE / "manual_image_index" / "pages.tsv"
XLSX_IMAGES = BASE / "xlsx_image_index" / "images.tsv"
OUT_DIR = BASE / "vision_index"
VISION_SCRIPT = Path(
    os.environ.get(
        "KB_VISION_SCRIPT",
        r"C:\Users\ASUS\.codex\skills\vision-skill\scripts\vision.js",
    )
)
NODE = Path(
    os.environ.get(
        "KB_NODE",
        r"C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe",
    )
)
DEFAULT_PROMPT = "用中文描述这张图片的内容，说明它展示的是什么（产品部位/操作步骤/故障现象/规格图等），并尽量保留图中可见的文字信息。"

_extract_lock = threading.Lock()


def load_tsv(path: Path, cols):
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            rows.append(r)
    return rows


def xlsx_extract_media(xlsx: Path, media_file: str, extract_dir: Path):
    """Extract one media file from the xlsx into extract_dir (cached)."""
    target = extract_dir / Path(media_file).name
    if target.exists() and target.stat().st_size > 0:
        return target
    with _extract_lock:
        if target.exists() and target.stat().st_size > 0:
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(xlsx) as z:
            src = "xl/" + media_file
            with z.open(src) as s, target.open("wb") as d:
                d.write(s.read())
    return target


def vision_describe(image_path: Path, prompt: str, retries: int = 2):
    """Describe an image using vision-skill (fallback). Raises on failure."""
    if not VISION_SCRIPT.exists():
        raise FileNotFoundError(
            "本会话不具备识图能力，且未安装 vision-skill 技能。"
            "请先安装 vision-skill（接入第三方识图 API）后再运行，"
            "或使用支持多模态的模型直接看图。"
        )
    if not NODE.exists():
        raise FileNotFoundError(f"未找到 Node.js: {NODE}")
    cmd = [str(NODE), str(VISION_SCRIPT), str(image_path), prompt]
    last_err = ""
    for attempt in range(retries + 1):
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", timeout=180
            )
            if proc.returncode == 0:
                return proc.stdout.strip()
            last_err = (proc.stderr or proc.stdout or "").strip()[:500]
        except subprocess.TimeoutExpired:
            last_err = "timeout"
        except Exception as e:
            last_err = str(e)[:500]
        if attempt < retries:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(last_err or "vision call failed")


def load_existing(shard: str = ""):
    """Return set of already-indexed (source, image_rel) pairs.

    Rows with any status (ok or fail) are considered attempted and skipped
    on resume; a targeted --force pass can retry failures after the merge.
    """
    done = set()
    tsv = OUT_DIR / (f"shard_{shard}.tsv" if shard else "images.tsv")
    if not tsv.exists():
        return done
    with tsv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            status = (r.get("status") or "").strip()
            if status:
                done.add((r.get("source", ""), r.get("image_rel", "")))
    return done


def build_jobs(source: str):
    jobs = []  # (source, image_rel, local_path_or_None)
    if source in ("manual", "all"):
        for r in load_tsv(MANUAL_PAGES, None):
            rel = (r.get("page_image_rel") or "").strip()
            if not rel:
                continue
            p = BASE / "pdf_pages" / rel
            if p.exists():
                jobs.append(("manual", rel, p))
    if source in ("xlsx", "all"):
        seen_media = set()
        for r in load_tsv(XLSX_IMAGES, None):
            media = (r.get("media_file") or "").strip()
            if not media or media in seen_media:
                continue
            seen_media.add(media)
            jobs.append(("xlsx", "xlsx:" + media, None))
    return jobs


def merge_shards():
    merged = {}
    for tsv in [OUT_DIR / "images.tsv"] + sorted(OUT_DIR.glob("shard_*.tsv")):
        for r in load_tsv(tsv, None):
            key = (r.get("source", ""), r.get("image_rel", ""))
            if key not in merged:
                merged[key] = r
    out_tsv = OUT_DIR / "images.tsv"
    with out_tsv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["source", "image_rel", "description", "model", "status", "generated_at"],
            delimiter="\t",
        )
        writer.writeheader()
        for r in merged.values():
            writer.writerow(r)
    ok = sum(1 for r in merged.values() if r.get("status") == "ok")
    fail = sum(1 for r in merged.values() if r.get("status", "").startswith("fail"))
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_unique": len(merged),
        "ok": ok,
        "fail": fail,
        "unattempted": sum(1 for r in merged.values() if not (r.get("status") or "").strip()),
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"merged: {len(merged)} unique, ok={ok}, fail={fail} -> {out_tsv}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["manual", "xlsx", "all"], default="manual")
    parser.add_argument("--filter", default="", help="only rows whose image_rel contains this substring")
    parser.add_argument("--limit", type=int, default=0, help="max images to process this run")
    parser.add_argument("--force", action="store_true", help="re-describe already indexed images")
    parser.add_argument("--workers", type=int, default=1, help="parallel vision calls")
    parser.add_argument("--retry-fail", action="store_true", help="only re-process rows whose status starts with fail")
    parser.add_argument("--split", type=int, default=1, help="total number of shards")
    parser.add_argument("--split-index", type=int, default=0, help="this run's shard index (0-based)")
    parser.add_argument("--shard", default="", help="shard name for output files (e.g. p0)")
    parser.add_argument("--status", action="store_true", help="only print pending count and exit")
    parser.add_argument("--merge", action="store_true", help="merge shard files into images.tsv")
    args = parser.parse_args()

    if args.merge:
        return merge_shards()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_tsv = OUT_DIR / (f"shard_{args.shard}.tsv" if args.shard else "images.tsv")
    summary_json = OUT_DIR / (f"summary_{args.shard}.json" if args.shard else "summary.json")

    jobs = build_jobs(args.source)
    if args.filter:
        jobs = [j for j in jobs if args.filter in j[1]]
    jobs.sort(key=lambda j: (j[0], j[1]))
    if args.split > 1:
        jobs = [j for i, j in enumerate(jobs) if i % args.split == args.split_index]

    attempted = load_existing(args.shard)
    if args.force:
        done = set()
    elif args.retry_fail:
        done = set()
        with (OUT_DIR / (f"shard_{args.shard}.tsv" if args.shard else "images.tsv")).open(
            "r", encoding="utf-8", newline=""
        ) as f:
            reader = csv.DictReader(f, delimiter="\t")
            for r in reader:
                if not (r.get("status") or "").startswith("fail"):
                    done.add((r.get("source", ""), r.get("image_rel", "")))
    else:
        done = attempted
    pending = [j for j in jobs if (j[0], j[1]) not in done]
    if args.limit > 0:
        pending = pending[: args.limit]

    print(
        f"shard={args.shard or '-'} jobs={len(jobs)} pending={len(pending)} "
        f"(filter={args.filter or '-'}, limit={args.limit or '-'}, workers={args.workers})"
    )
    if args.status:
        print(f"STATUS pending={len(pending)}")
        return 0
    if not pending:
        print("nothing to do")
        return 0

    status = {"ok": 0, "fail": 0}
    errors = []
    write_lock = threading.Lock()
    extract_dir = OUT_DIR / "media"
    xlsx_candidates = list(BASE.glob("日本站售后对应方案表*.xlsx"))
    xlsx = xlsx_candidates[0] if xlsx_candidates else None

    def process_one(item):
        source, rel, p = item
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if source == "xlsx" and p is None:
            if xlsx is None:
                return [source, rel, "", "", "fail:no-xlsx", now]
            media = rel.split(":", 1)[1]
            try:
                p = xlsx_extract_media(xlsx, media, extract_dir)
            except Exception as e:
                return [source, rel, "", "", "fail:extract:" + str(e)[:150], now]
        try:
            desc = vision_describe(p, DEFAULT_PROMPT)
            return [source, rel, desc.replace("\n", " "), "vision-skill/qwen", "ok", now]
        except Exception as e:
            return [source, rel, "", "", "fail:" + str(e)[:200], now]

    with out_tsv.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        if out_tsv.stat().st_size == 0:
            writer.writerow(["source", "image_rel", "description", "model", "status", "generated_at"])

        if args.workers <= 1:
            for i, item in enumerate(pending, 1):
                row = process_one(item)
                with write_lock:
                    writer.writerow(row)
                    if row[4] == "ok":
                        status["ok"] += 1
                    else:
                        status["fail"] += 1
                        errors.append({"source": row[0], "image_rel": row[1], "error": row[4]})
                        print(f"  FAIL {row[0]} {row[1]}: {row[4]}")
                if i % 5 == 0 or i == len(pending):
                    print(f"  progress {i}/{len(pending)} ok={status['ok']} fail={status['fail']}")
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
                futures = {ex.submit(process_one, item): item for item in pending}
                done_count = 0
                for fut in concurrent.futures.as_completed(futures):
                    row = fut.result()
                    with write_lock:
                        writer.writerow(row)
                        f.flush()
                        if row[4] == "ok":
                            status["ok"] += 1
                        else:
                            status["fail"] += 1
                            errors.append({"source": row[0], "image_rel": row[1], "error": row[4]})
                            print(f"  FAIL {row[0]} {row[1]}: {row[4]}")
                    done_count += 1
                    if done_count % 10 == 0 or done_count == len(pending):
                        print(f"  progress {done_count}/{len(pending)} ok={status['ok']} fail={status['fail']}")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": args.source,
        "shard": args.shard,
        "split": args.split,
        "split_index": args.split_index,
        "jobs_total": len(jobs),
        "processed": len(pending),
        "ok": status["ok"],
        "fail": status["fail"],
        "errors": errors[:20],
    }
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done: processed={len(pending)} ok={status['ok']} fail={status['fail']} -> {out_tsv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
