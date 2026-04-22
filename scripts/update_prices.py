#!/usr/bin/env python3
"""
市场价格更新工具

遍历 components_lib.csv 全量条目，通过网络搜索查询当前市场价，
更新 cost_min / cost_max，并将变动记录到 data/lib/price_history.csv。

用法：
    python scripts/update_prices.py                    # 全量刷新
    python scripts/update_prices.py --bucket cleaning  # 只刷指定桶
    python scripts/update_prices.py --dry-run          # 只打印，不写入
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import anthropic

ROOT          = Path(__file__).parent.parent
LIB_CSV       = ROOT / "data" / "lib" / "components_lib.csv"
HISTORY_CSV   = ROOT / "data" / "lib" / "price_history.csv"

TODAY = date.today().isoformat()

HISTORY_FIELDS = [
    "date", "id", "bom_bucket", "name", "model_numbers", "spec",
    "old_cost_min", "old_cost_max", "new_cost_min", "new_cost_max",
    "source", "note",
]

LIB_FIELDS = [
    "id", "bom_bucket", "bom_bucket_cn", "name", "name_en",
    "tier", "model_numbers", "spec", "cost_min", "cost_max", "unit",
    "suppliers", "confidence", "models", "last_updated",
]


# ── Anthropic 客户端 ────────────────────────────────────────────────

def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _search_price(client: anthropic.Anthropic, row: dict) -> tuple[Optional[float], Optional[float], str]:
    """
    用 web_search 查询单个零件当前市场价。
    返回 (cost_min, cost_max, note)，查询失败返回 (None, None, 错误信息)。
    """
    name        = row["name"]
    model_no    = row.get("model_numbers", "")
    spec        = row.get("spec", "")
    suppliers   = row.get("suppliers", "")
    bucket      = row.get("bom_bucket", "")

    # 构造搜索描述
    parts = [name]
    if model_no:
        parts.append(model_no)
    if spec:
        parts.append(spec)
    if suppliers:
        parts.append(f"品牌：{suppliers}")

    query_desc = "、".join(parts)

    # 桶级别补充背景（帮助模型理解采购量级）
    bucket_context = {
        "compute_electronics": "消费电子主板级芯片，千片以上批量采购价",
        "perception":          "传感器模组，千片批量采购价",
        "power_motion":        "电机/风机，千片批量采购价",
        "cleaning":            "清洁执行件，千片批量采购价",
        "dock_station":        "基站零部件，千片批量采购价",
        "energy":              "电池/BMS，千片批量采购价",
        "structure_cmf":       "结构件/外壳，千片批量采购价",
        "mva_software":        "组装人工/软件授权，单件成本",
    }.get(bucket, "千片批量采购价")

    prompt = (
        f"请搜索以下扫地机器人零部件的当前中国市场批量采购价（{bucket_context}）：\n\n"
        f"零件描述：{query_desc}\n\n"
        "要求：\n"
        "1. 优先参考立创商城、淘宝企业采购、1688、电子发烧友等渠道的近期价格\n"
        "2. 给出价格区间（最低价 ~ 最高价），单位：人民币元/件\n"
        "3. 只输出以下格式，不要其他文字：\n"
        "   MIN: <数字>\n"
        "   MAX: <数字>\n"
        "   NOTE: <简短说明（来源/时间/置信度）>\n"
        "4. 若无法查到价格，输出：MIN: 0  MAX: 0  NOTE: 未找到"
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            tools=[{
                "name": "web_search",
                "type": "web_search_20250305",
            }],
            messages=[{"role": "user", "content": prompt}],
        )

        # 提取文本输出
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        min_m = re.search(r"MIN:\s*([\d.]+)", text)
        max_m = re.search(r"MAX:\s*([\d.]+)", text)
        note_m = re.search(r"NOTE:\s*(.+)", text)

        cost_min = float(min_m.group(1)) if min_m else None
        cost_max = float(max_m.group(1)) if max_m else None
        note     = note_m.group(1).strip() if note_m else "解析失败"

        if cost_min == 0 and cost_max == 0:
            return None, None, note

        return cost_min, cost_max, note

    except Exception as e:
        return None, None, f"查询异常: {e}"


# ── 历史记录 ────────────────────────────────────────────────────────

def _append_history(records: list[dict]) -> None:
    write_header = not HISTORY_CSV.exists()
    with HISTORY_CSV.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(records)


# ── 主流程 ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="市场价格更新工具")
    parser.add_argument("--bucket",  help="只刷新指定 bom_bucket（如 cleaning）")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写入文件")
    args = parser.parse_args()

    if not LIB_CSV.exists():
        print(f"找不到标准件库：{LIB_CSV}")
        sys.exit(1)

    rows: list[dict] = []
    with LIB_CSV.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if args.bucket:
        target = [r for r in rows if r["bom_bucket"] == args.bucket]
        print(f"过滤桶 {args.bucket}：{len(target)} / {len(rows)} 条")
    else:
        target = rows

    print(f"开始价格更新：{len(target)} 条零件\n{'─'*60}")

    client     = _client()
    history    = []
    updated    = 0
    skipped    = 0
    row_index  = {r["id"]: r for r in rows}

    for i, row in enumerate(target, 1):
        rid  = row["id"]
        name = row["name"]
        mn   = row.get("model_numbers", "")
        label = f"{name}（{mn}）" if mn else name

        print(f"[{i:3d}/{len(target)}] {label}")

        new_min, new_max, note = _search_price(client, row)

        if new_min is None:
            print(f"       ⚠ 跳过：{note}\n")
            skipped += 1
            continue

        old_min = row.get("cost_min", "")
        old_max = row.get("cost_max", "")

        changed = (str(new_min) != str(old_min)) or (str(new_max) != str(old_max))
        flag = "↻ 更新" if changed else "= 不变"
        print(f"       {flag}  ¥{old_min}~{old_max} → ¥{new_min}~{new_max}  [{note}]\n")

        history.append({
            "date":         TODAY,
            "id":           rid,
            "bom_bucket":   row["bom_bucket"],
            "name":         name,
            "model_numbers": mn,
            "spec":         row.get("spec", ""),
            "old_cost_min": old_min,
            "old_cost_max": old_max,
            "new_cost_min": new_min,
            "new_cost_max": new_max,
            "source":       "web_search",
            "note":         note,
        })

        if not args.dry_run and changed:
            row_index[rid]["cost_min"]     = new_min
            row_index[rid]["cost_max"]     = new_max
            row_index[rid]["last_updated"] = TODAY
            updated += 1

    # 写回 components_lib.csv
    if not args.dry_run and updated > 0:
        with LIB_CSV.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=LIB_FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"✓ components_lib.csv 已更新：{updated} 条变动")
    elif args.dry_run:
        print("dry-run 模式，未写入文件")
    else:
        print("价格无变动，未写入文件")

    # 写入历史
    if not args.dry_run and history:
        _append_history(history)
        print(f"✓ price_history.csv 已追加：{len(history)} 条记录")

    print(f"\n完成：更新 {updated} 条，跳过 {skipped} 条")


if __name__ == "__main__":
    main()
