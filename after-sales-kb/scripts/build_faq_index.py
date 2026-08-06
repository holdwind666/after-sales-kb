"""Parse cached kdocs sheet texts into per-product FAQ JSON files."""
import json
import re
from pathlib import Path

KDOCS_DIR = Path(r"E:\说明书与视频（第9台）\_售后模板缓存\kdocs")
OUT_DIR = Path(r"E:\说明书与视频（第9台）\_售后模板缓存\faq")


def clean_cell(value: str) -> str:
    """Strip whitespace and collapse internal runs of whitespace."""
    value = (value or "").strip()
    return re.sub(r"[ \t\r\n]+", " ", value)


def split_rows(text: str):
    """Split kdocs clipboard text into rows of cells.

    The clipboard dump is TSV-like: cells are separated by tabs, rows by
    newlines, and quoted cells may contain tabs/newlines. A state machine
    splits on tab/newline only when not inside a double-quoted cell.
    """
    rows = []
    cells = []
    buf = ""
    in_quotes = False
    for ch in text:
        if ch == '"':
            in_quotes = not in_quotes
            buf += ch
        elif ch == "\t" and not in_quotes:
            cells.append(buf)
            buf = ""
        elif ch == "\n" and not in_quotes:
            cells.append(buf)
            rows.append(cells)
            cells = []
            buf = ""
        else:
            buf += ch
    if buf or cells:
        cells.append(buf)
        rows.append(cells)
    return rows


def unquote_cell(raw: str) -> str:
    """Remove wrapping quotes and unescape doubled quotes."""
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        raw = raw[1:-1]
    return raw.replace('""', '"')


def parse_sheet_text(text: str):
    """Parse one sheet text into a list of cleaned cell-row lists."""
    parsed = []
    for row in split_rows(text):
        cells = [clean_cell(unquote_cell(c)) for c in row]
        if any(cells):
            parsed.append(cells)
    return parsed


def is_header_row(cells) -> bool:
    joined = "".join(cells)
    has_date = ("日期" in joined) or ("更新月份" in joined)
    has_cols = ("模板" in joined) or ("对应方法" in joined) or ("担当" in joined) or ("问题" in joined)
    return has_date and has_cols


def build_column_map(header_cells) -> dict:
    mapping = {}
    for i, cell in enumerate(header_cells):
        c = cell.strip()
        if not c:
            continue
        if c.startswith("日期") or c.startswith("更新月份"):
            mapping["date"] = i
        elif c.startswith("故障类型") or c.startswith("类型"):
            mapping["category"] = i
        elif c.startswith("担当") or c.startswith("负责人"):
            mapping["owner"] = i
        elif c.startswith("问题"):
            mapping["question"] = i
        elif c.startswith("对应方法") or c.startswith("处理方法") or c.startswith("对策"):
            mapping["answer"] = i
        elif c.startswith("模板") or c.startswith("回复") or c.startswith("文案"):
            mapping["template"] = i
        elif c.startswith("ASIN"):
            mapping["asin"] = i
        elif c.startswith("品名") or c.startswith("商品"):
            mapping["product"] = i
    return mapping


def map_row(cells, col_map) -> dict:
    def get(key):
        idx = col_map.get(key)
        if idx is None or idx >= len(cells):
            return ""
        return cells[idx].strip()

    row = {
        "date": get("date"),
        "category": get("category"),
        "owner": get("owner"),
        "question": get("question"),
        "answer": get("answer"),
        "template": get("template"),
        "asin": get("asin"),
        "product": get("product"),
        "media": [],
    }
    for c in cells:
        if "DISPIMG" in c or c.startswith("ID_"):
            row["media"].append(c.strip())
    return row


def fallback_row(cells) -> dict:
    non_empty = [c for c in cells if c]
    row = {
        "date": "",
        "category": "",
        "owner": "",
        "question": "",
        "answer": "",
        "template": "",
        "asin": "",
        "product": "",
        "media": [],
    }
    if not non_empty:
        return row
    if re.match(r"20\d{2}[/\-.]\d{1,2}[/\-.]\d{1,2}", non_empty[0]):
        row["date"] = non_empty[0]
        non_empty = non_empty[1:]
    if non_empty:
        row["question"] = non_empty[0]
    if len(non_empty) > 1:
        row["answer"] = " | ".join(non_empty[1:])
    return row


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(KDOCS_DIR.glob("*.txt"))
    stats = []
    total_rows = 0
    for f in files:
        if f.name == "_capture_log.txt":
            continue
        text = f.read_text(encoding="utf-8")
        rows = parse_sheet_text(text)

        header_idx = None
        for i, cells in enumerate(rows[:10]):
            if is_header_row(cells):
                header_idx = i
                break

        col_map = build_column_map(rows[header_idx]) if header_idx is not None else {}
        data_rows = []
        for i, cells in enumerate(rows):
            if header_idx is not None and i == header_idx:
                continue
            non_empty = [c for c in cells if c]
            if not non_empty:
                continue
            # Skip pure media rows (image refs only)
            if all("DISPIMG" in c or c.startswith("ID_") for c in non_empty):
                continue
            if col_map:
                row = map_row(cells, col_map)
                # Skip rows whose date/question/answer are all media refs
                text_fields = [row[k] for k in ("date", "category", "owner", "question", "answer", "template", "asin", "product")]
                has_real_text = any(k and "DISPIMG" not in k and not k.startswith("ID_") for k in text_fields)
                if not has_real_text:
                    continue
                data_rows.append(row)
            else:
                data_rows.append(fallback_row(cells))

        sheet_name = f.stem
        out_file = OUT_DIR / f"{sheet_name}.json"
        payload = {"sheet": sheet_name, "source": f.name, "items": data_rows}
        out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        total_rows += len(data_rows)
        stats.append((sheet_name, len(data_rows), out_file.stat().st_size))

    print(f"done: {len(stats)} sheets, {total_rows} rows total")
    for name, n, size in stats:
        print(f"{name}: {n} rows, {size} bytes")


if __name__ == "__main__":
    main()
