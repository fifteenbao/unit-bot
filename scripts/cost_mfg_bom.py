#!/usr/bin/env python3
"""
制造BOM成本分析器 — 解析量产BOM CSV → 归桶定价 → 7桶成本汇总

支持格式: 金蝶/SAP等ERP导出的层级BOM (含"层级"/"物料名称"/"规格型号"/"供应方式"列)

用法:
    python scripts/cost_mfg_bom.py data/bom/C33.csv
    python scripts/cost_mfg_bom.py data/bom/C33.csv --msrp 2999 --model "C33"
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from collections import defaultdict


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.bom_rules import (
    BUCKET_DEFAULT_PRICE,
    BUCKET_MIN_FLOOR_COST,
    classify,
    is_aux,
    aux_price,
)
from core.components_lib import load_lib
from core.bucket_framework import (
    buckets_ordered,
    bucket_pct_range,
    estimate_level1_costs,
)

DATA_DIR  = ROOT / "data"
PARTS_FILE = DATA_DIR / "lib" / "standard_parts.json"

BUCKETS = buckets_ordered()
BUCKET_KEYS = [k for k, _ in BUCKETS]


# ── 辅助 ─────────────────────────────────────────────────────────────

def _mid(lo: float, hi: float) -> float:
    if lo == 0 and hi == 0:
        return 0.0
    if lo == 0:
        return hi
    if hi == 0:
        return lo
    return (lo + hi) / 2


def _mid_lib(row: dict) -> float:
    try:
        lo = float(row.get("cost_min") or 0)
        hi = float(row.get("cost_max") or 0)
    except ValueError:
        return 0.0
    return _mid(lo, hi)


def _load_standard_parts() -> dict:
    if PARTS_FILE.exists():
        return json.loads(PARTS_FILE.read_text(encoding="utf-8"))
    return {}


def _build_lib_index() -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for row in load_lib():
        b = row.get("bom_bucket", "")
        idx.setdefault(b, []).append(row)
    return idx


def _norm(s: str) -> str:
    return re.sub(r"[\s/+\-·()（）]+", "", (s or "")).lower()


def _lookup_price(
    name: str, spec: str, bucket: str, hint: str,
    lib_index: dict, parts_json: dict,
    used_ids: set,
) -> tuple[float, str]:
    """三级查价: lib → standard_parts → 桶兜底。"""
    blob = f"{name} {spec}"
    candidates = lib_index.get(bucket, [])

    # Tier 1: hint → lib name 子串
    if hint:
        for lib_row in candidates:
            lname = lib_row.get("name", "")
            if lname and hint in lname:
                if lib_row["id"] in used_ids:
                    return BUCKET_DEFAULT_PRICE.get(bucket, 1.0), f"default:{bucket}(防重)"
                p = _mid_lib(lib_row)
                if p:
                    used_ids.add(lib_row["id"])
                    return p, f"lib:{lib_row['id']}(hint)"

    # Tier 2: name 完全匹配
    name_norm = _norm(name)
    for lib_row in candidates:
        lname = lib_row.get("name", "")
        if lname and _norm(lname) == name_norm:
            if lib_row["id"] in used_ids:
                return BUCKET_DEFAULT_PRICE.get(bucket, 1.0), f"default:{bucket}(防重)"
            p = _mid_lib(lib_row)
            if p:
                used_ids.add(lib_row["id"])
                return p, f"lib:{lib_row['id']}"

    # Tier 3: lib name 子串匹配 blob
    for lib_row in candidates:
        lname = lib_row.get("name", "")
        if not lname or len(lname) < 3:
            continue
        if lname in name or lname in blob:
            if lib_row["id"] in used_ids:
                return BUCKET_DEFAULT_PRICE.get(bucket, 1.0), f"default:{bucket}(防重)"
            p = _mid_lib(lib_row)
            if p:
                used_ids.add(lib_row["id"])
                return p, f"lib:{lib_row['id']}(子串)"

    # Tier 4: standard_parts.json
    for group, items in parts_json.items():
        if not isinstance(items, list):
            continue
        for it in items:
            if it.get("bom_bucket") != bucket:
                continue
            it_name = it.get("name", "")
            if it_name and len(it_name) >= 3 and it_name in name:
                price = it.get("price_1k") or (it.get("price_range") or [None])[0]
                if price:
                    return float(price), f"std:{group}/{it_name}"

    # Tier 5: 桶兜底
    return BUCKET_DEFAULT_PRICE.get(bucket, 1.0), f"default:{bucket}"


# ── MFG BOM 解析 ─────────────────────────────────────────────────────

def _detect_columns(fieldnames: list[str]) -> dict[str, str]:
    """从表头自动检测关键列名映射。"""
    mapping = {}
    for f in fieldnames:
        fn = f.strip()
        if re.search(r"^层级$|^Level$", fn):
            mapping["level"] = f
        elif re.search(r"物料名称|零件名|Name", fn):
            mapping["name"] = f
        elif re.search(r"规格型号|型号|Spec", fn):
            mapping["spec"] = f
        elif re.search(r"^标准用量$|^用量$|^Qty$|数量", fn):
            mapping["qty"] = f
        elif re.search(r"供应方式|采购方式|Sourcing", fn):
            mapping["sourcing"] = f
        elif re.search(r"供应商|Supplier", fn):
            mapping["supplier"] = f
        elif re.search(r"物料编码|料号|PN|Part.*No", fn):
            mapping["pn"] = f
    return mapping


def load_mfg_bom(path: Path) -> list[dict]:
    """加载制造BOM，仅保留叶节点(无子件的最底层)。"""
    with open(path, encoding="utf-8-sig") as f:
        raw_lines = f.readlines()

    # 自动跳过首行标题行（如"BOM正查"），找到真正含列名的表头行
    header_idx = 0
    for i, line in enumerate(raw_lines):
        fields = [c.strip() for c in line.split(",")]
        if any(re.search(r"物料名称|层级|序号", f) for f in fields):
            header_idx = i
            break

    import io
    content = "".join(raw_lines[header_idx:])
    reader = csv.DictReader(io.StringIO(content))
    fieldnames = reader.fieldnames or []
    col = _detect_columns(list(fieldnames))
    rows = list(reader)

    if not col.get("name"):
        raise ValueError(f"找不到物料名称列，表头: {fieldnames}")

    # 解析 level 列为整数
    parsed = []
    for r in rows:
        level_raw = r.get(col.get("level", ""), "").strip()
        try:
            lvl = int(float(level_raw))
        except (ValueError, TypeError):
            lvl = -1
        parsed.append({
            "level":    lvl,
            "name":     r.get(col.get("name", ""), "").strip(),
            "spec":     r.get(col.get("spec", ""), "").strip(),
            "qty":      r.get(col.get("qty", ""), "1").strip() or "1",
            "sourcing": r.get(col.get("sourcing", ""), "").strip(),
            "supplier": r.get(col.get("supplier", ""), "").strip(),
            "pn":       r.get(col.get("pn", ""), "").strip(),
            "_raw":     r,
        })

    # 定价粒度: level 2 (子部件). level>2 的 SMT 元件/原材料不单独计价.
    # 逻辑: 对每个 level in [1,2] 的行, 若下一行 level<=当前 OR 下一行 level>2, 视为"叶".
    MAX_PRICE_LEVEL = 2
    leaves = []
    for i, row in enumerate(parsed):
        lvl = row["level"]
        if lvl <= 0 or lvl > MAX_PRICE_LEVEL:
            continue
        if i + 1 < len(parsed):
            next_lvl = parsed[i + 1]["level"]
            is_leaf = (next_lvl <= lvl) or (next_lvl > MAX_PRICE_LEVEL)
        else:
            is_leaf = True
        if is_leaf:
            leaves.append(row)

    return leaves


# ── 主分析流程 ───────────────────────────────────────────────────────

def analyze(bom_path: Path, msrp: float | None, model: str) -> None:
    print(f"\n{'='*60}")
    print(f"  制造BOM成本分析: {model}")
    print(f"  来源: {bom_path.name}")
    print(f"{'='*60}\n")

    leaves = load_mfg_bom(bom_path)
    print(f"  解析到 {len(leaves)} 个叶节点零件\n")

    lib_index  = _build_lib_index()
    parts_json = _load_standard_parts()

    # 每桶独立 used_ids，防止同类整机唯一件重复计价
    used_ids: dict[str, set] = {k: set() for k in BUCKET_KEYS}

    bucket_cost:  dict[str, float] = defaultdict(float)
    bucket_items: dict[str, list]  = defaultdict(list)
    unclassified: list[dict] = []

    for row in leaves:
        name    = row["name"]
        spec    = row["spec"]
        sourcing = row["sourcing"]

        # 跳过顶层组件 (委外/成品, 层级 ≥ 2 时才可能是真实叶节点)
        if not name or name.startswith("晓舞") or name.startswith("C33"):
            continue

        # 辅料检测
        if is_aux(name):
            unit_price = aux_price(name, spec)
            try:
                qty = max(1, int(float(row["qty"] or 1)))
            except (ValueError, TypeError):
                qty = 1
            line_cost = unit_price * qty
            # 辅料归入 structure_cmf
            bucket_cost["structure_cmf"] += line_cost
            bucket_items["structure_cmf"].append({
                "name": name, "spec": spec, "qty": qty,
                "unit_price": unit_price, "line_cost": line_cost,
                "src": "aux", "sourcing": sourcing,
            })
            continue

        # classify() 内部拼 blob="name||spec", 导致 ^name$ 锚定失效.
        # 先只用 name 单独测试正则，再回落到 classify(name, spec_clean).
        from core.bom_rules import KEYWORD_RULES as _KR
        bucket = hint = note = None
        for _pat, _bkt, _hnt, _nt in _KR:
            if re.search(_pat, name):
                bucket, hint, note = _bkt, _hnt, _nt
                break
        if bucket is None:
            spec_clean = re.sub(r"^[\w\-]+[、,，]", "", spec).strip()
            bucket, hint, note = classify(name, spec_clean)
        if bucket is None:
            unclassified.append(row)
            continue

        # PCBA组件 (完整PCBA组件) 与 PCB裸板区分: 用专有 hint 指向含SMT的 lib 条目
        if re.search(r"^PCBA组件$", name) and re.search(r"主板|主机.*板", spec):
            hint = "主板PCB(PCBA组件)"

        try:
            qty = max(1, int(float(row["qty"] or 1)))
        except (ValueError, TypeError):
            qty = 1

        unit_price, src = _lookup_price(
            name, spec, bucket, hint,
            lib_index, parts_json,
            used_ids[bucket],
        )
        line_cost = unit_price * qty
        bucket_cost[bucket] += line_cost
        bucket_items[bucket].append({
            "name": name, "spec": spec[:40] if spec else "",
            "qty": qty, "unit_price": unit_price,
            "line_cost": line_cost, "src": src,
            "sourcing": sourcing,
        })

    # 地板保护
    for bkt in BUCKET_KEYS:
        floor = BUCKET_MIN_FLOOR_COST.get(bkt, 0)
        if 0 < bucket_cost[bkt] < floor:
            bucket_cost[bkt] = floor

    bom_total = sum(bucket_cost.values())

    # ── 打印桶明细 ────────────────────────────────────────────────────
    print(f"  {'桶':<20} {'金额(元)':>8}  {'占BOM%':>6}  {'件数':>4}  {'理论区间':>12}")
    print(f"  {'-'*60}")
    for bkt, name_cn in BUCKETS:
        cost  = bucket_cost.get(bkt, 0.0)
        pct   = cost / bom_total * 100 if bom_total else 0
        cnt   = len(bucket_items.get(bkt, []))
        lo, hi = bucket_pct_range(bkt)
        theory = f"{lo*100:.0f}%~{hi*100:.0f}%"
        flag = " ⚠" if (pct < lo*100*0.7 or pct > hi*100*1.3) and cost > 0 else ""
        print(f"  {name_cn:<20} {cost:>8.1f}  {pct:>5.1f}%  {cnt:>4}  {theory:>12}{flag}")

    print(f"  {'-'*60}")
    print(f"  {'BOM合计':<20} {bom_total:>8.1f}")
    if msrp:
        ratio = bom_total / msrp * 100
        print(f"  {'MSRP':.<20} {msrp:>8.0f}")
        print(f"  {'BOM/MSRP':.<20} {ratio:>7.1f}%")

    # ── 打印各桶Top件 ────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print("  各桶 Top 件明细")
    print(f"{'─'*60}")
    for bkt, name_cn in BUCKETS:
        items = sorted(bucket_items.get(bkt, []), key=lambda x: -x["line_cost"])
        if not items:
            continue
        print(f"\n  [{name_cn}]  合计 ¥{bucket_cost[bkt]:.1f}")
        for it in items[:8]:
            src_tag = f"({it['src']})" if not it['src'].startswith("lib:") else ""
            print(f"    ¥{it['line_cost']:>6.1f}  {it['name'][:30]:<30}  ×{it['qty']}  {src_tag}")

    # ── 未归桶件 ─────────────────────────────────────────────────────
    if unclassified:
        print(f"\n{'─'*60}")
        print(f"  未归桶零件 ({len(unclassified)} 件，未计入BOM):")
        for row in unclassified[:20]:
            print(f"    - {row['name'][:50]}  [{row['spec'][:30]}]")
        if len(unclassified) > 20:
            print(f"    ... 还有 {len(unclassified)-20} 件")

    # ── 一级成本结构 ─────────────────────────────────────────────────
    if msrp:
        print(f"\n{'='*60}")
        print("  成本结构估算")
        print(f"{'='*60}")
        l1 = estimate_level1_costs(bom_total, msrp)
        meta = l1.get("整机全成本 (估算)", {})
        full_cost = meta.get("cost", 0)
        cogs      = meta.get("cogs", 0)
        opex      = meta.get("opex", 0)

        # COGS 分项
        COGS_ITEMS = {"硬件物料 (7桶)", "人工+机器折旧", "仓储物流售后"}
        OPEX_ITEMS = {"销售+管理费用", "研发均摊"}

        print(f"\n  ── 营业成本 COGS ──────────────────────────────")
        for cat, vals in l1.items():
            if cat not in COGS_ITEMS:
                continue
            amt = vals.get("cost", 0)
            pct_msrp = amt / msrp * 100
            src = vals.get("source", "")
            print(f"  {cat:<20} ¥{amt:>6.0f}  ({pct_msrp:.1f}% of MSRP)  [{src}]")
        pct_cogs = cogs / msrp * 100
        print(f"  {'COGS 小计':<20} ¥{cogs:>6.0f}  ({pct_cogs:.1f}% of MSRP)")

        print(f"\n  ── 期间费用 OpEx ──────────────────────────────")
        for cat, vals in l1.items():
            if cat not in OPEX_ITEMS:
                continue
            amt = vals.get("cost", 0)
            pct_msrp = amt / msrp * 100
            src = vals.get("source", "")
            print(f"  {cat:<20} ¥{amt:>6.0f}  ({pct_msrp:.1f}% of MSRP)  [{src}]")
        pct_opex = opex / msrp * 100
        print(f"  {'期间费用小计':<20} ¥{opex:>6.0f}  ({pct_opex:.1f}% of MSRP)")

        gross_margin = (msrp - cogs) / msrp * 100
        net_margin   = (msrp - full_cost) / msrp * 100
        print(f"\n  {'─'*46}")
        print(f"  MSRP                 ¥{msrp:>6.0f}")
        print(f"  毛利润 (MSRP-COGS)   ¥{msrp-cogs:>6.0f}  毛利率 {gross_margin:.1f}%")
        print(f"  净利润 (扣期间费用)   ¥{msrp-full_cost:>6.0f}  净利率 {net_margin:.1f}%")

    print()


# ── CLI ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="制造BOM成本分析")
    parser.add_argument("bom_csv", type=Path, help="制造BOM CSV路径")
    parser.add_argument("--msrp",  type=float, help="建议零售价 (元)")
    parser.add_argument("--model", type=str,   help="机型名称 (默认从文件名推断)")
    args = parser.parse_args()

    if not args.bom_csv.exists():
        print(f"错误: 文件不存在 {args.bom_csv}", file=sys.stderr)
        sys.exit(1)

    model = args.model or args.bom_csv.stem
    analyze(args.bom_csv, args.msrp, model)


if __name__ == "__main__":
    main()
