"""Remove failed placeholder rows from the merged vision index.

Keeps only rows with status == 'ok', rewrites images.tsv and summary.json.
Also removes shard_*.tsv / summary_*.json so a later --merge cannot
re-introduce failed rows from the aborted full-vision run.
"""

import csv
import json
from datetime import datetime, timezone
from kb_paths import cache_root

BASE = cache_root()
TSV = BASE / "vision_index" / "images.tsv"
SUMMARY = BASE / "vision_index" / "summary.json"
FIELDS = ["source", "image_rel", "description", "model", "status", "generated_at"]


def main():
    # Remove shard files first so merge later only uses the cleaned images.tsv.
    for shard in (BASE / "vision_index").glob("shard_*.tsv"):
        shard.unlink()
        print(f"REMOVED_SHARD: {shard.name}")
    for sm in (BASE / "vision_index").glob("summary_*.json"):
        if sm.name != "summary.json":
            sm.unlink()
            print(f"REMOVED_SUMMARY: {sm.name}")

    rows = []
    with TSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            rows.append(r)

    ok_rows = [r for r in rows if r.get("status") == "ok"]
    with TSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(ok_rows)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "policy": "ocr_first_vision_on_demand",
        "total_ok": len(ok_rows),
        "failed_rows_cleaned": len(rows) - len(ok_rows),
        "note": "Failed rows from the aborted full-vision run were removed; only successfully described images are kept.",
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK_ROWS: {len(ok_rows)}")
    print(f"CLEANED: {len(rows) - len(ok_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
