"""
扫地机器人 BOM 8 桶成本分析框架加载器。

数据源: core/bom_8bucket_framework.json (版本化的标准模板, 与本模块同目录)
消费者: scripts/gen_teardown.py (拆机 BOM 生成), scripts/analyze_*.py (成本分析)

配套的 data/lib/bom_8bucket_framework.csv 是给人看/对账填价用的工作表,
不由本模块消费; 如模板有变, 用 scripts/export_framework_csv.py 重新生成。

提供:
  - load_framework(): 加载原始 JSON
  - buckets_ordered(): 按 order 返回 [(key, cn_name), ...]
  - bucket_pct_range(key): 返回 (low, high) 行业占比小数
  - render_prompt_bucket_section(): 生成给 LLM 的桶清单文本
  - audit_coverage(rows): 对一份 BOM 行检查每桶子项覆盖缺口
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

FRAMEWORK_FILE = Path(__file__).parent / "bom_8bucket_framework.json"


@lru_cache(maxsize=1)
def load_framework() -> dict:
    return json.loads(FRAMEWORK_FILE.read_text(encoding="utf-8"))


def buckets_ordered() -> list[tuple[str, str]]:
    """按 order 返回 [(key, name_cn), ...]"""
    fw = load_framework()
    items = sorted(fw["buckets"].items(), key=lambda kv: kv[1]["order"])
    return [(k, b["name_cn"]) for k, b in items]


def bucket_pct_range(key: str) -> tuple[float, float]:
    """返回 (low, high) 小数形式, 例如 (0.10, 0.15)"""
    b = load_framework()["buckets"][key]
    lo, hi = b["industry_pct_range"]
    return lo / 100.0, hi / 100.0


def bucket_pct_avg(key: str) -> float:
    """返回平均占比小数"""
    return load_framework()["buckets"][key]["industry_pct_avg"] / 100.0


def typical_item_names(key: str) -> list[str]:
    """返回某桶的典型子项名列表"""
    return [it["name"] for it in load_framework()["buckets"][key]["typical_items"]]


def render_prompt_bucket_section() -> str:
    """生成 LLM prompt 中的桶清单文本块, 含定义+典型子项+边界说明。"""
    fw = load_framework()
    lines: list[str] = []
    for _, b in sorted(fw["buckets"].items(), key=lambda kv: kv[1]["order"]):
        key = b["name_en"].lower().replace(" ", "_").replace("+", "_")
        # 直接用 JSON 里的 key (更稳定)
        lines.append(f"- **{b['order']}. {b['name_cn']}** ({b['industry_pct_avg']}%)")
        lines.append(f"  定义: {b['definition']}")
        items = "、".join(it["name"] for it in b["typical_items"])
        lines.append(f"  典型子项: {items}")
        if b.get("boundary_notes"):
            lines.append(f"  边界: {b['boundary_notes'][0]}")
        lines.append("")
    return "\n".join(lines).rstrip()


def bucket_keys() -> list[str]:
    fw = load_framework()
    return [k for k, _ in sorted(fw["buckets"].items(), key=lambda kv: kv[1]["order"])]


def audit_coverage(rows: list[dict], bucket_field: str = "bom_bucket",
                   name_field: str = "name") -> dict:
    """
    对照 framework 的 typical_items, 检查每桶覆盖缺口。
    返回 {bucket: {"count": n, "present": [...], "missing": [...], "status": "✓/△/⚠"}}。

    覆盖判定: typical_item 的 name 关键词 (取前 4 字) 出现在任意行的 name 中即算 present。
    """
    fw = load_framework()
    result: dict[str, dict] = {}

    # 按桶归集行
    by_bucket: dict[str, list[dict]] = {k: [] for k in fw["buckets"]}
    for r in rows:
        b = (r.get(bucket_field) or "").strip()
        if b in by_bucket:
            by_bucket[b].append(r)

    for bkey, bdef in fw["buckets"].items():
        bucket_rows = by_bucket[bkey]
        names_blob = " ".join((r.get(name_field) or "") for r in bucket_rows)
        present, missing = [], []
        for it in bdef["typical_items"]:
            # 取子项名前 4 字作为关键词 (避免"主控 SoC" vs "SoC" 这种漏匹)
            key_frag = it["name"].replace(" ", "").replace("/", "")[:4]
            if key_frag and key_frag in names_blob.replace(" ", ""):
                present.append(it["name"])
            else:
                missing.append(it["name"])

        count = len(bucket_rows)
        if count == 0:
            status = "⚠ 无数据"
        elif len(missing) > len(bdef["typical_items"]) * 0.6:
            status = f"△ 覆盖不全 ({len(present)}/{len(bdef['typical_items'])})"
        else:
            status = f"✓ 覆盖 {len(present)}/{len(bdef['typical_items'])}"

        result[bkey] = {
            "name_cn": bdef["name_cn"],
            "count": count,
            "present": present,
            "missing": missing,
            "pct_avg": bdef["industry_pct_avg"],
            "status": status,
        }
    return result
