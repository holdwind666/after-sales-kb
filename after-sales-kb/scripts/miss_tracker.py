"""Cross-conversation miss counter for the after-sales knowledge base.

Usage:
  python miss_tracker.py status
  python miss_tracker.py record --product "06 switch手柄" --question "充電できない" --reason "no template hit"
  python miss_tracker.py acknowledge
  python miss_tracker.py reset

Reminder policy:
  - When the record count reaches the threshold (default 3), reminder_due is set.
  - reminder_due stays True on every subsequent record until the user
    actually completes the incremental update and runs acknowledge (or
    update-done). This means every later miss keeps prompting for an
    incremental update, instead of silently re-accumulating.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SETTINGS = BASE / "settings.json"
COUNTER = BASE / "miss_counter.json"


def load_settings():
    if SETTINGS.exists():
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    return {"miss_threshold": 3}


def load_counter():
    if COUNTER.exists():
        return json.loads(COUNTER.read_text(encoding="utf-8"))
    return {"records": [], "reminder_due": False, "last_reminder": None, "cycles": 0}


def save_counter(data):
    COUNTER.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def print_status(data, settings):
    threshold = settings.get("miss_threshold", 3)
    print(f"records: {len(data['records'])} / {threshold}")
    print(f"reminder_due: {data['reminder_due']}")
    print(f"last_reminder: {data['last_reminder']}")
    print(f"cycles: {data['cycles']}")
    for r in data["records"]:
        print(f"  - [{r['timestamp']}] {r.get('product','')} | {r.get('question','')} | {r.get('reason','')}")
    if data["reminder_due"]:
        print("ACTION: remind user to consider incremental update")
        print("NOTE: if the user has NOT performed the incremental update, every subsequent miss will keep reminding until acknowledge.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "record", "acknowledge", "update-done", "reset"])
    parser.add_argument("--product", default="")
    parser.add_argument("--question", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()

    settings = load_settings()
    data = load_counter()
    threshold = settings.get("miss_threshold", 3)

    if args.action == "status":
        print_status(data, settings)
        return

    if args.action == "reset":
        save_counter({"records": [], "reminder_due": False, "last_reminder": None, "cycles": data.get("cycles", 0)})
        print("reset done")
        return

    if args.action in ("acknowledge", "update-done"):
        data["reminder_due"] = False
        data["last_reminder"] = datetime.now().isoformat(timespec="seconds")
        data["cycles"] = data.get("cycles", 0) + 1
        data["records"] = []
        save_counter(data)
        print("acknowledged (incremental update completed), counter reset")
        return

    if args.action == "record":
        data["records"].append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "product": args.product,
            "question": args.question,
            "reason": args.reason,
        })
        if len(data["records"]) >= threshold:
            data["reminder_due"] = True
        save_counter(data)
        print_status(data, settings)


if __name__ == "__main__":
    main()
