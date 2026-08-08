"""Import ChatGPT conversation exports (official or browser-extension JSON/JSONL)
into the WPS-synced raw directory so the standard learning pipeline can consume
them. This is the "方案 B" (fast export) path.

Supported inputs:
  - Official export: conversations.json (array of conversation objects)
  - Official export: conversations.jsonl (one conversation per line)
  - Extension export: a folder of *.json / *.jsonl files (one conversation
    per file/line), including per-project folders (project title is taken
    from the folder name).

Output:
  raw/conv_<id>.json          full conversation payload (UTF-8, no BOM)
  raw/conv_<id>.meta.json     optional project metadata
  raw/state.json              updated seen/pending bookkeeping

Usage:
  python import_chatgpt_export.py --source <file-or-folder> --config <cfg>
  python import_chatgpt_export.py --source <file-or-folder> --raw <raw_dir>
"""

import argparse
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def read_json_text(path: Path):
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    obj = json.loads(text)
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            pass
    return obj


def norm_ts(ts):
    if ts is None:
        return ""
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        except Exception:
            return str(ts)
    return str(ts)


def fallback_id(obj, title, create_time):
    raw = f"{title}|{create_time}"
    return "imp_" + hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def collect_input_files(source: Path):
    """Return (path, project_title) candidates, JSONL first for priority."""
    if source.is_file():
        return [(source, "")]
    out = []
    for p in sorted(source.rglob("conversations.json")):
        out.append((p, ""))
    for p in sorted(source.rglob("conversations.jsonl")):
        out.append((p, ""))
    for p in sorted(source.rglob("*.json")):
        if p.name in ("conversations.json",):
            continue
        if p.name.endswith(".meta.json"):
            continue
        rel = p.relative_to(source)
        project = str(rel.parent) if str(rel.parent) != "." else ""
        out.append((p, project))
    for p in sorted(source.rglob("*.jsonl")):
        if p.name == "conversations.jsonl":
            continue
        rel = p.relative_to(source)
        project = str(rel.parent) if str(rel.parent) != "." else ""
        out.append((p, project))
    return out


def iter_payloads(path: Path):
    """Yield conversation dicts from a file."""
    if path.suffix.lower() == ".jsonl":
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, str):
                    obj = json.loads(obj)
                yield obj
            except Exception:
                continue
        return
    try:
        obj = read_json_text(path)
    except Exception:
        return
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                yield item
    elif isinstance(obj, dict):
        # Some exports wrap a list under a key.
        for key in ("conversations", "items", "data"):
            if isinstance(obj.get(key), list):
                for item in obj[key]:
                    if isinstance(item, dict):
                        yield item
                return
        yield obj


def load_state(state_path: Path):
    state = {"seen": {}, "pending": []}
    if not state_path.exists():
        return state
    try:
        old = read_json_text(state_path)
        if isinstance(old, dict):
            if isinstance(old.get("seen"), dict):
                state["seen"] = {str(k): str(v) for k, v in old["seen"].items()}
            if isinstance(old.get("pending"), list):
                state["pending"] = [str(x) for x in old["pending"]]
    except Exception:
        pass
    return state


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--config", default="")
    ap.add_argument("--raw", default="")
    ap.add_argument("--project", default="", help="only import conversations belonging to this project folder name")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    source = Path(args.source)
    if not source.exists():
        print(f"ERROR: source not found: {source}")
        return 1

    raw_dir = Path(args.raw) if args.raw else Path("")
    if (not args.raw or str(raw_dir) in ("", ".")) and args.config:
        try:
            cfg = read_json_text(Path(args.config))
            raw_dir = Path(cfg.get("raw_dir") or "")
        except Exception:
            raw_dir = Path("")
    if not str(raw_dir) or str(raw_dir) == ".":
        print("ERROR: no raw_dir; pass --config or --raw")
        return 1
    raw_dir.mkdir(parents=True, exist_ok=True)

    state_path = raw_dir / "state.json"
    state = load_state(state_path)
    seen = state["seen"]
    pending = state["pending"]

    imported = 0
    skipped = 0
    failed = 0
    files = collect_input_files(source)
    for path, folder_project in files:
        for obj in iter_payloads(path):
            if not isinstance(obj, dict):
                continue
            title = str(obj.get("title") or "")
            create_time = norm_ts(obj.get("create_time"))
            update_time = norm_ts(obj.get("update_time"))
            cid = str(obj.get("id") or fallback_id(obj, title, create_time))

            project_title = ""
            if args.project:
                if args.project not in str(folder_project) and args.project not in title:
                    continue
            if folder_project:
                project_title = folder_project
            meta = obj.get("meta")
            if isinstance(meta, dict) and meta.get("project_title"):
                project_title = str(meta["project_title"])

            if not args.force and seen.get(cid) == update_time:
                skipped += 1
                continue
            try:
                out_file = raw_dir / f"conv_{cid}.json"
                out_file.write_text(
                    json.dumps(obj, ensure_ascii=False, indent=1),
                    encoding="utf-8",
                )
                if project_title:
                    meta_path = raw_dir / f"conv_{cid}.meta.json"
                    meta_path.write_text(
                        json.dumps({"project_title": project_title}, ensure_ascii=False),
                        encoding="utf-8",
                    )
                seen[cid] = update_time
                if cid in pending:
                    pending.remove(cid)
                imported += 1
            except Exception as e:
                failed += 1
                print(f"FAIL {path.name} {cid}: {e}")

    state_path.write_text(
        json.dumps({"seen": seen, "pending": pending,
                    "last_import": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    print("IMPORT_DONE")
    print(f"SOURCE={source}")
    print(f"FILES={len(files)} IMPORTED={imported} SKIPPED={skipped} FAILED={failed}")
    print(f"RAW_DIR={raw_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
