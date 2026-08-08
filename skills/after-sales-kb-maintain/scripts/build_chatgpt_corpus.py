"""Build the ChatGPT-history learning corpus for the after-sales KB.

Inputs:
  raw/conv_<id>.json          - full conversation payloads (from capture script)
  raw/conv_<id>.meta.json     - optional project metadata
  feedback/*.jsonl            - user-curated success cases (schema below)

Outputs (corpus/):
  chatgpt_full.jsonl          - work-related conversations (messages preserved)
  chatgpt_norm.tsv            - quick-query search rows (id, title, project, text)
  template_pairs.tsv          - user question -> assistant reply pairs
  persona.md                  - virtual after-sales agent role card
  summary.json                - statistics for diagnostics
  relevance_report.tsv        - every conversation + relevance + reason (audit)

Feedback JSONL schema (one JSON per line):
  {"date":"2026-08-07","product":"6228折叠吹风机",
   "issue":"風量を調整できない","chinese_logic":"...",
   "japanese_reply":"お客様 ...","result":"customer_satisfied"}
"""

import argparse
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

WORK_KEYWORDS = [
    # 售后/客服
    "售后", "返品", "返金", "交換", "新品", "発送", "配送", "到着", "商品", "不良",
    "故障", "保証", "レビュー", "星", "評価", "お客様", "申し訳", "アマゾン",
    "amazon", "asin", "領星", "注文", "注文番号", "物流", "邮便番号", "住所",
    "電話番号", "部品", "説明書", "取扱説明書", "充電", "バッテリー", "電源",
    "お手入れ", "フィルター", "風量", "温度", "モード", "ボタン", "ランプ",
    "ドライヤー", "扇風機", "サーキュレーター", "加湿器", "空気清浄機", "電動",
    "吹风机", "循环扇", "加湿器", "空气净化器", "充电", "说明书", "配件",
    "退货", "退款", "发新", "补发", "赔偿", "客户", "客人", "亚马逊", "差评",
    "模板", "回复", "日文", "日本語", "中文", "翻译", "话术", "対応", "お問い合わせ",
    # 运营/选品/竞品/广告/库存
    "运营", "listing", "标题", "五点", "关键词", "关键词", "文案", "图片", "主图",
    "A+", "竞品", "競合", "调研", "市场", "選品", "选品", "销量", "売上", "销售",
    "排名", "ランキング", "bsr", "秒杀", "deal", "クーポン", "优惠券", "广告",
    "広告", "ppc", "cpc", "转化", "転換", "点击", "クリック", "库存", "在庫",
    "补货", "入荷", "発注", "fba", "fbm", "海外仓", "仓库", "倉庫", "物流单号",
    "SKU", "sku", "upc", "ean", "品牌", "ブランド", "パッケージ", "包装",
    "说明书", "说明书修改", "取扱説明書", "规格书", "仕様書", "发票", "領収書",
]

IRRELEVANT_HINTS = [
    "菜谱", "食谱", "做饭", "旅游", "旅行", "电影", "音乐", "游戏攻略",
    "学习英语", "背单词", "健身", "减肥", "恋爱", "天气", "新闻", "明星",
    "八卦", "笑话", "故事", "作文", "PPT模板", "简历", "面试", "考研",
]


def read_json(path: Path):
    """Read JSON tolerant of a UTF-8 BOM (PowerShell Set-Content emits one)."""
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    obj = json.loads(text)
    # playwright-cli may write the payload as a JSON string rather than an
    # object; unwrap it so extract_messages sees a dict.
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            pass
    return obj


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def text_of(part):
    """Best-effort extraction of text from a ChatGPT message content part."""
    if part is None:
        return ""
    if isinstance(part, str):
        return part
    if isinstance(part, list):
        return " ".join(text_of(x) for x in part)
    if isinstance(part, dict):
        for key in ("text", "content", "value"):
            if key in part:
                v = text_of(part[key])
                if v:
                    return v
        if part.get("content_type") in ("text", "code"):
            return text_of(part.get("text", ""))
    return ""


def message_text(msg):
    """Extract the full user-facing text of a message dict."""
    if not isinstance(msg, dict):
        return ""
    if isinstance(msg.get("content"), str):
        return msg["content"]
    content = msg.get("content")
    if isinstance(content, dict):
        parts = content.get("parts")
        if parts is None and content.get("content_type") == "text":
            parts = content.get("text")
        if parts is None and "text" in content:
            parts = content["text"]
        return text_of(parts)
    if isinstance(content, list):
        return text_of(content)
    return ""


def role_of(msg):
    author = msg.get("author") or {}
    role = author.get("role") or msg.get("role") or ""
    return str(role).lower()


def walk_mapping(payload):
    """Return ordered (role, text) list from the legacy mapping tree."""
    mapping = payload.get("mapping") or {}
    if not mapping:
        return []
    current = payload.get("current_node")
    if not current:
        # Fall back to any node with a terminal child chain.
        parents = {v.get("parent"): k for k, v in mapping.items() if v.get("parent")}
        current = next(iter(set(mapping) - set(parents)), None)
    out = []
    seen = set()
    while current and current not in seen:
        seen.add(current)
        node = mapping.get(current)
        if not node:
            break
        msg = node.get("message")
        if msg:
            role = role_of(msg)
            text = message_text(msg)
            if role in ("user", "assistant") and text.strip():
                out.append((role, text))
        current = node.get("parent")
    out.reverse()
    return out


def extract_messages(payload):
    """Return ordered (role, text) pairs for any payload shape we know."""
    if not isinstance(payload, dict):
        return []
    linear = payload.get("linear_conversation")
    if isinstance(linear, list):
        out = []
        for item in linear:
            if not isinstance(item, dict):
                continue
            role = role_of(item)
            text = message_text(item)
            if role in ("user", "assistant") and text.strip():
                out.append((role, text))
        return out
    if isinstance(payload.get("messages"), list):
        out = []
        for item in payload["messages"]:
            if not isinstance(item, dict):
                continue
            role = role_of(item)
            text = message_text(item)
            if role in ("user", "assistant") and text.strip():
                out.append((role, text))
        return out
    if payload.get("mapping"):
        return walk_mapping(payload)
    return []


def classify(text: str, title: str):
    """Return (relevance, reason). 1 = work, 0 = irrelevant."""
    hay = norm(text + " " + title)
    work_hits = [k for k in WORK_KEYWORDS if norm(k) in hay]
    irrelevant_hits = [k for k in IRRELEVANT_HINTS if norm(k) in hay]
    if irrelevant_hits and len(work_hits) < len(irrelevant_hits):
        return 0, "irrelevant:" + ",".join(irrelevant_hits[:5])
    if work_hits:
        return 1, "work:" + ",".join(work_hits[:8])
    # No strong signal: default to work for a work account, but mark it.
    return 1, "unclear:no_strong_signal"


def load_feedback(feedback_dir: Path):
    rows = []
    if not feedback_dir.exists():
        return rows
    for p in sorted(feedback_dir.glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def stats_and_persona(work_rows, feedback_rows, out_dir: Path):
    total = len(work_rows)
    feedback_total = len(feedback_rows)
    user_chars = 0
    assistant_chars = 0
    templates = 0
    for row in work_rows:
        for role, text in row["messages"]:
            if role == "user":
                user_chars += len(text)
            else:
                assistant_chars += len(text)
        for msg in row["messages"]:
            if msg[0] == "assistant" and re.search(r"お客様|申し訳|ご返金|新品|発送", msg[1]):
                templates += 1
                break

    project_counter = Counter(row.get("project_title") or "未分类" for row in work_rows)
    top_projects = project_counter.most_common(12)

    phrase_counter = Counter()
    PHRASES = [
        "お客様", "この度は", "誠に申し訳ございません", "申し訳ございません",
        "何卒よろしくお願い申し上げます", "何卒よろしくお願い致します",
        "恐れ入りますが", "お世話になっております", "ご確認ください",
        "お手数ですが", "新品", "返金", "発送", "交換", "弊社は中古品を販売しておりません",
        "ご返信ありがとうございます", "お問い合わせいただき", "承知いたしました",
    ]
    for row in work_rows:
        for role, text in row["messages"]:
            if role != "assistant":
                continue
            for phrase in PHRASES:
                if phrase in text:
                    phrase_counter[phrase] += 1
    top_phrases = phrase_counter.most_common(10)

    persona = f"""# 虚拟客服角色卡（从 ChatGPT 历史对话学习生成）

> 由 build_chatgpt_corpus.py 从 {total} 段工作相关对话自动提炼。
> 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}
> 本卡是“你”这个售后客服在历史处理中表现出的风格与逻辑的浓缩，供生成回复时参考。

## 你是谁

- 你是日本站 Amazon 店铺的售后客服，处理日文顾客咨询，同时用中文内部沟通。
- 你对顾客礼貌、诚恳、先致歉再解释；对内简洁、按证据办事。
- 你熟悉公司产品（吹风机、循环扇、加湿器、空气净化器等）和常见售后场景（故障、返品、返金、差评、发新）。

## 历史对话规模（最近一次学习）

- 工作相关对话：{total}
- 人工反馈案例：{feedback_total}
- 累计用户字符数：{user_chars}
- 累计助手字符数：{assistant_chars}
- 含日文售后回复的对话：{templates}
- 主要项目：{", ".join(f"{p}({c})" for p, c in top_projects)}

## 高频用语（来自历史回复统计）

{chr(10).join("- " + p + "：" + str(c) + " 次" for p, c in top_phrases) if top_phrases else "- 暂无足够样本，先采用下方通用习惯。"}

## 回复逻辑（从成功案例归纳，按优先级）

1. 先致歉/感谢，再说明事实，不推诿。
2. 能直接答的产品问题直接答；需要确认的先给“确认步骤 + 让顾客拍视频/照片”的引导。
3. 故障类：先引导排查（使用方式、清洁、模式），确认后给方案（发新/退款/补偿），能补发配件优先补发。
4. 外箱破损/配送类：先说明配送冲击可能，强调“弊社は中古品を販売しておりません”，再给分层方案（保留+补偿 500-1000 円 / 发新 / 全额退款）。
5. 规格与页面信息不一致：承认页面问题并道歉，给出现行规格说明，按需补偿或退款。
6. 差评类：先了解具体不满，结合正确使用方式二次说明，再引导评价修改，绝不硬性承诺。
7. 日文模板用语习惯：お客様 ／ この度は ／ 誠に申し訳ございません ／ 何卒よろしくお願い申し上げます ／ 恐れ入りますが。

## 语气风格

- 使用敬体（です・ます），礼貌词密度高。
- 段落短，善用 ① ② ③ 或 【】 分点。
- 对顾客给“选项”而不是只给结论：保留补偿 / 发新 / 退款。
- 需要顾客配合时明确写“お手数ですが…ご確認いただけますでしょうか”。

## 从历史中强化学习的建议

- 查询时优先看 corpus/template_pairs.tsv 里相同问题的完整日文模板。
- 生成回复后，把最终采用的中文逻辑 + 日文回复写入 feedback/*.jsonl 并重跑构建，让角色卡持续成长。
"""
    (out_dir / "persona.md").write_text(persona, encoding="utf-8")
    return persona


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="")
    ap.add_argument("--raw", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--include-irrelevant", action="store_true",
                    help="also index clearly irrelevant conversations (default: exclude)")
    args = ap.parse_args()

    config = {}
    if args.config:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    cloud_root = config.get("cloud_root", "")
    raw_dir = Path(args.raw or config.get("raw_dir") or (Path(cloud_root) / "raw" if cloud_root else ""))
    out_dir = Path(args.out or config.get("corpus_dir") or (Path(cloud_root) / "corpus" if cloud_root else ""))
    feedback_dir = Path(config.get("feedback_dir") or (Path(cloud_root) / "feedback" if cloud_root else ""))

    if not raw_dir.exists():
        print("ERROR: raw_dir not found:", raw_dir)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    full_path = out_dir / "chatgpt_full.jsonl"
    norm_path = out_dir / "chatgpt_norm.tsv"
    pairs_path = out_dir / "template_pairs.tsv"
    report_path = out_dir / "relevance_report.tsv"

    work_rows = []
    report_lines = []
    pairs = []

    conv_files = sorted(p for p in raw_dir.glob("conv_*.json") if not p.name.endswith(".meta.json"))
    for p in conv_files:
        try:
            payload = read_json(p)
        except Exception as e:
            report_lines.append(f"{p.name}\tparse_error\t{e}")
            continue
        conv_id = p.name[len("conv_"):-len(".json")]
        meta = {}
        meta_path = raw_dir / (p.name[:-5] + ".meta.json")
        if meta_path.exists():
            try:
                meta = read_json(meta_path)
            except Exception:
                meta = {}

        title = payload.get("title") or meta.get("title") or conv_id
        create_time = payload.get("create_time") or ""
        update_time = payload.get("update_time") or ""
        if isinstance(create_time, (int, float)):
            create_time = datetime.fromtimestamp(create_time).strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(update_time, (int, float)):
            update_time = datetime.fromtimestamp(update_time).strftime("%Y-%m-%d %H:%M:%S")

        messages = extract_messages(payload)
        if not messages:
            report_lines.append(f"{p.name}\tno_messages\t{title}")
            continue

        all_text = "\n".join(t for _, t in messages)
        relevance, reason = classify(all_text, str(title))
        report_lines.append(f"{p.name}\t{relevance}\t{reason}\t{title}")
        if relevance == 0 and not args.include_irrelevant:
            continue

        row = {
            "id": conv_id,
            "title": title,
            "project_id": meta.get("project_id", ""),
            "project_title": meta.get("project_title", ""),
            "create_time": create_time,
            "update_time": update_time,
            "relevance": relevance,
            "reason": reason,
            "messages": messages,
        }
        work_rows.append(row)

        for i, (role, text) in enumerate(messages):
            if role != "assistant" or i == 0:
                continue
            if not re.search(r"お客様|申し訳|ご返金|新品|発送|交換|お願い", text):
                continue
            q = messages[i - 1][1] if messages[i - 1][0] == "user" else ""
            if not q.strip():
                continue
            pairs.append((q.replace("\t", " ").replace("\n", " ")[:1000],
                          text.replace("\t", " ").replace("\n", " ")[:4000],
                          conv_id, str(title)))

    # Feedback cases always participate (curated = high confidence).
    feedback_rows = load_feedback(feedback_dir)
    for fb in feedback_rows:
        q = fb.get("chinese_logic") or fb.get("issue") or ""
        a = fb.get("japanese_reply") or ""
        row = {
            "id": "feedback_" + (fb.get("date") or datetime.now().strftime("%Y%m%d")),
            "title": fb.get("product", ""),
            "project_id": "",
            "project_title": "人工反馈",
            "create_time": fb.get("date", ""),
            "update_time": "",
            "relevance": 1,
            "reason": "feedback:curated",
            "messages": [("user", q), ("assistant", a)],
        }
        work_rows.append(row)
        if a:
            pairs.append((q.replace("\t", " ").replace("\n", " ")[:1000],
                          a.replace("\t", " ").replace("\n", " ")[:4000],
                          row["id"], row["title"]))

    # Write full JSONL (filtered to work conversations).
    with full_path.open("w", encoding="utf-8") as f:
        for row in work_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Write norm TSV for quick_query.
    with norm_path.open("w", encoding="utf-8") as f:
        for row in work_rows:
            text = "\n".join(t for _, t in row["messages"]).replace("\t", " ").replace("\n", " ")
            f.write("\t".join([
                row["id"],
                (row["title"] or "").replace("\t", " "),
                (row["project_title"] or "").replace("\t", " "),
                text[:6000],
            ]) + "\n")

    # Write template pairs.
    with pairs_path.open("w", encoding="utf-8") as f:
        f.write("question\tanswer\tconv_id\ttitle\n")
        for q, a, cid, title in pairs:
            f.write("\t".join([q, a, cid, title]) + "\n")

    # Write relevance report.
    with report_path.open("w", encoding="utf-8") as f:
        f.write("file\trelevance\treason\ttitle\n")
        for line in report_lines:
            f.write(line + "\n")

    # Persona + summary.
    stats_and_persona(work_rows, feedback_rows, out_dir)
    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "raw_files": len(conv_files),
        "work_conversations": sum(1 for r in work_rows if not r["id"].startswith("feedback_")),
        "feedback_cases": len(feedback_rows),
        "template_pairs": len(pairs),
        "irrelevant_skipped": sum(1 for line in report_lines if "\t0\t" in line),
        "total_messages": sum(len(r["messages"]) for r in work_rows),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("BUILD_DONE")
    print(f"RAW_FILES={len(conv_files)}")
    print(f"WORK_CONVERSATIONS={summary['work_conversations']}")
    print(f"FEEDBACK_CASES={summary['feedback_cases']}")
    print(f"TEMPLATE_PAIRS={summary['template_pairs']}")
    print(f"IRRELEVANT_SKIPPED={summary['irrelevant_skipped']}")
    print(f"OUT_DIR={out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
