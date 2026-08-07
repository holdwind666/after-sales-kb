#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_manual_images.py

说明书图文关联索引：
  1. 扫描 pdf_ocr/*.txt，按 "===== PAGE N =====" 标记切分 OCR 文本段；
  2. 扫描 pdf_pages/ 下所有 jpg/png，按文件名提取 PDF 基础名与页序号；
  3. 将 OCR 文本段与页图按出现顺序一一对齐（第 k 段 <-> 第 k 张页图），
     多余页图/多余段保留为 unmatched 并计入统计，不报错；
  4. 输出 manual_image_index/pages.tsv、manuals.tsv、summary.json；
  5. 打印每个文件与全库统计。

只读源目录：pdf_ocr/ 与 pdf_pages/
所有运行输出仅写入：manual_image_index/
仅使用 Python 标准库（pathlib / re / csv / json）。
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

CACHE_ROOT = Path(r"E:\说明书与视频（第9台）\_售后模板缓存")
OCR_DIR = CACHE_ROOT / "pdf_ocr"
PAGES_DIR = CACHE_ROOT / "pdf_pages"
OUT_DIR = CACHE_ROOT / "manual_image_index"

PAGE_MARKER_RE = re.compile(r"^\s*=====\s*PAGE\s+(\d+)\s*=====\s*$", re.MULTILINE)
IMAGE_NAME_RE = re.compile(
    r"^(?P<base>.+)_p-(?P<num>\d+)\.(?P<ext>jpg|jpeg|png)$", re.IGNORECASE
)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
PREVIEW_LEN = 80


def read_text(path: Path) -> str:
    """读取 OCR 文本；UTF-8 失败时改用 errors="replace" 容错继续。"""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def split_ocr_segments(text: str) -> list[tuple[str, str]]:
    """按 '===== PAGE N =====' 切分 OCR 文本段。

    无标记 -> 整篇视为一段（页序=1，标记=空）。
    有标记 -> 每个标记对应一段；第一个标记之前的内容并入第一段，
    这样例如 S1（PAGE 1,3,...,35 共 18 个标记）正好得到 18 段。
    返回 [(文本内容, 标记号)]，空白段也保留。
    """
    matches = list(PAGE_MARKER_RE.finditer(text))
    if not matches:
        return [(text, "")]

    segments: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end]
        if i == 0:
            content = text[: m.start()] + content
        segments.append((content, m.group(1)))
    return segments


def sanitize_preview(value: str) -> str:
    """预览列去掉制表符与换行，避免破坏 TSV 行结构。"""
    return value.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def scan_ocr() -> dict[str, list[tuple[str, str]]]:
    """pdf_base -> OCR 段列表（按文件内出现顺序）。"""
    result: dict[str, list[tuple[str, str]]] = {}
    for path in sorted(OCR_DIR.glob("*.txt")):
        result[path.stem] = split_ocr_segments(read_text(path))
    return result


def scan_images() -> tuple[dict[str, list[tuple[int, str]]], list[str]]:
    """pdf_base -> [(页序号, 相对 pdf_pages 的路径)]；另返回无法解析的图片。"""
    images: dict[str, list[tuple[int, str]]] = {}
    unparsed: list[str] = []
    for path in sorted(PAGES_DIR.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        rel = str(path.relative_to(PAGES_DIR))
        m = IMAGE_NAME_RE.match(path.name)
        if not m:
            unparsed.append(rel)
            continue
        images.setdefault(m.group("base"), []).append((int(m.group("num")), rel))
    for base in images:
        images[base].sort(key=lambda item: item[0])
    return images, unparsed


def main() -> int:
    if not OCR_DIR.is_dir() or not PAGES_DIR.is_dir():
        print(f"缺少源目录：OCR={OCR_DIR} 页图={PAGES_DIR}")
        return 1

    ocr_by_base = scan_ocr()
    images_by_base, unparsed_images = scan_images()
    all_bases = sorted(set(ocr_by_base) | set(images_by_base))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    page_rows: list[list[str]] = []
    manual_rows: list[list[str]] = []

    total_pages = 0
    total_images = 0
    matched_pairs = 0
    unmatched_images = 0
    unmatched_segments = 0

    for base in all_bases:
        segments = ocr_by_base.get(base, [])
        images = images_by_base.get(base, [])
        ocr_file = OCR_DIR / f"{base}.txt" if base in ocr_by_base else None

        n_seg = len(segments)
        n_img = len(images)
        n_matched = min(n_seg, n_img)
        page_count = max(n_seg, n_img)

        total_pages += page_count
        total_images += n_img
        matched_pairs += n_matched
        unmatched_segments += n_seg - n_matched
        unmatched_images += n_img - n_matched

        # 匹配对：第 k 段 <-> 第 k 张页图
        for k in range(n_matched):
            seg_text, marker = segments[k]
            page_seq, image_rel = images[k]
            page_rows.append(
                [
                    base,
                    str(page_seq),
                    marker,
                    str(len(seg_text)),
                    sanitize_preview(seg_text[:PREVIEW_LEN]),
                    image_rel,
                    "1",
                ]
            )

        # 多余 OCR 段：无页图
        for k in range(n_matched, n_seg):
            seg_text, marker = segments[k]
            page_rows.append(
                [
                    base,
                    str(k + 1),
                    marker,
                    str(len(seg_text)),
                    sanitize_preview(seg_text[:PREVIEW_LEN]),
                    "",
                    "0",
                ]
            )

        # 多余页图：无 OCR 段
        for k in range(n_matched, n_img):
            page_seq, image_rel = images[k]
            page_rows.append(
                [base, str(page_seq), "", "", "", image_rel, "0"]
            )

        manual_rows.append(
            [
                base,
                ocr_file.name if ocr_file else "",
                str(page_count),
                str(n_seg),
                str(n_img),
                str(n_matched),
            ]
        )

        print(f"{base}\t页段数={n_seg}\t页图数={n_img}\t匹配数={n_matched}")

    if unparsed_images:
        total_images += len(unparsed_images)
        unmatched_images += len(unparsed_images)
        print(
            "未按文件名解析的页图（计入未匹配图片）："
            + "、".join(unparsed_images)
        )

    summary = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total_pdfs": len(all_bases),
        "total_pages": total_pages,
        "total_images": total_images,
        "matched_pairs": matched_pairs,
        "unmatched_images": unmatched_images,
        "unmatched_segments": unmatched_segments,
    }

    with open(OUT_DIR / "pages.tsv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "pdf_base",
                "page_seq",
                "ocr_page_marker",
                "ocr_text_len",
                "ocr_preview",
                "page_image_rel",
                "matched",
            ]
        )
        writer.writerows(page_rows)

    with open(OUT_DIR / "manuals.tsv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "pdf_base",
                "ocr_text_file",
                "page_count",
                "ocr_segments",
                "image_count",
                "matched_count",
            ]
        )
        writer.writerows(manual_rows)

    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("--- 全库统计 ---")
    print(f"PDF 数: {summary['total_pdfs']}")
    print(f"总页数: {summary['total_pages']}")
    print(f"总图片数: {summary['total_images']}")
    print(f"总匹配对: {summary['matched_pairs']}")
    print(f"未匹配图片数: {summary['unmatched_images']}")
    print(f"未匹配段数: {summary['unmatched_segments']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
