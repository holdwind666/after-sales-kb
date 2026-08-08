"""Track cache misses in the configured per-device cache."""

import argparse
import json
from datetime import datetime

from kb_paths import cache_root, load_config

BASE = cache_root()
SETTINGS = load_config()
COUNTER = BASE / "miss_counter.json"


def load_counter():
    if COUNTER.exists():
        return json.loads(COUNTER.read_text(encoding="utf-8-sig"))
    return {"records": [], "reminder_due": False, "last_reminder": None, "cycles": 0}


def save_counter(data):
    COUNTER.parent.mkdir(parents=True, exist_ok=True)
    COUNTER.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def print_status(data, threshold):
    print(f"records: {len(data['records'])} / {threshold}")
    print(f"reminder_due: {data['reminder_due']}")
    print(f"last_reminder: {data['last_reminder']}")
    print(f"cycles: {data['cycles']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "record", "acknowledge", "update-done", "reset"])
    parser.add_argument("--product", default="")
    parser.add_argument("--question", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    threshold = int(SETTINGS.get("miss_threshold", 3))
    data = load_counter()
    if args.action == "status":
        print_status(data, threshold)
        return
    if args.action == "reset":
        save_counter({"records": [], "reminder_due": False, "last_reminder": None, "cycles": data.get("cycles", 0)})
        print("reset done")
        return
    if args.action in ("acknowledge", "update-done"):
        data.update({"records": [], "reminder_due": False, "last_reminder": datetime.now().isoformat(timespec="seconds"), "cycles": data.get("cycles", 0) + 1})
        save_counter(data)
        print("acknowledged")
        return
    data["records"].append({"timestamp": datetime.now().isoformat(timespec="seconds"), "product": args.product, "question": args.question, "reason": args.reason})
    if len(data["records"]) >= threshold:
        data["reminder_due"] = True
    save_counter(data)
    print_status(data, threshold)


if __name__ == "__main__":
    main()
