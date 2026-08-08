"""Extract quick-fact snippets from OCR texts, grouped by product and fact keyword."""
import json
import re
from kb_paths import cache_root

BASE = cache_root()
OCR = BASE / "pdf_ocr"
PAGES = BASE / "pdf_pages"
PRODUCTS_TSV = BASE / "products.tsv"
OUT_DIR = BASE / "facts"

FACT_KEYWORDS = {
    "充电时间": ["充電時間", "充电时间"],
    "充电指示": ["充電中", "満充電", "充电中", "充满", "点灯", "点滅"],
    "电池": ["電池容量", "電池種類", "バッテリー", "电池容量"],
    "尺寸重量": ["外形寸法", "質量", "重量", "サイズ", "尺寸"],
    "连接": ["ペアリング", "接続方法", "登録方法", "长按", "長押し", "连接方法"],
    "电源": ["定格電圧", "定格出力", "定格消費電力", "输入", "入力"],
    "线长": ["電源コード長", "電源側コード長", "本体側コード長", "コード長", "線長", "充電ケーブル", "电源线", "线长"],
    "温度": ["温度", "温度設定", "予熱", "预热"],
    "容量": ["タンク容量", "容量", "水箱"],
    "功能按键": ["TURBO", "連射", "连射", "マクロ", "宏", "M1", "M2", "振動", "震动"],
}


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def extract_snippets(text: str, keywords, window=140, max_per_kw=6):
    ntext = norm(text)
    results = []
    for kw in keywords:
        k = norm(kw)
        if not k:
            continue
        seen = set()
        start = 0
        count = 0
        while count < max_per_kw:
            idx = ntext.find(k, start)
            if idx < 0:
                break
            s = max(0, idx - 60)
            e = min(len(ntext), idx + len(k) + window)
            snippet = ntext[s:e]
            if snippet not in seen:
                seen.add(snippet)
                results.append({"kw": kw, "snippet": snippet})
                count += 1
            start = idx + len(k)
    return results


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Load product -> OCR file mapping from products.tsv
    product_ocr = {}
    if PRODUCTS_TSV.exists():
        lines = PRODUCTS_TSV.read_text(encoding="utf-8").splitlines()
        header = lines[0].split("\t")
        try:
            idx_product = header.index("product")
            idx_ocr = header.index("ocr_files")
        except ValueError:
            idx_product = idx_ocr = 0
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) <= max(idx_product, idx_ocr):
                continue
            product = parts[idx_product]
            ocr_names = [n for n in parts[idx_ocr].split("|") if n]
            product_ocr[product] = ocr_names

    stats = []
    for product, ocr_names in product_ocr.items():
        all_snippets = []
        for name in ocr_names:
            txt = OCR / name
            if not txt.exists():
                continue
            text = txt.read_text(encoding="utf-8", errors="replace")
            for kw_group, keywords in FACT_KEYWORDS.items():
                all_snippets.extend(extract_snippets(text, keywords))
        out = OUT_DIR / f"{product}.json"
        out.write_text(json.dumps({"product": product, "facts": all_snippets}, ensure_ascii=False, indent=1), encoding="utf-8")
        stats.append((product, len(all_snippets), out.stat().st_size))
    print(f"done: {len(stats)} products")
    for name, n, size in stats[:12]:
        print(f"{name}: {n} snippets, {size} bytes")


if __name__ == "__main__":
    main()
