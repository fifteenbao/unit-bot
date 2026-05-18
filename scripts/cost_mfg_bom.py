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
from core.process_lib import query_processes, query_molds, query_tooling

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


# ── Should Cost 估算 (材料 + 工艺 + 模具 + 工具 + 利润) ──────────────

_MOLD_RE = re.compile(r"模号[：:]\s*([A-Za-z0-9\-]+)")

# 工艺识别 → process_id
# 注意 1: 标件 (螺丝/螺钉/卡扣) 必须先于 spec 中的 "镀彩锌" 关键词匹配，避免把成品紧固件识别成镀锌工序
# 注意 2: 紧固件的镀层成本已含在 aux_price 内，aggregate 只算装配时间 (P_FAST_SCREW)
_NAME_FIRST_HINTS = [
    (r"螺丝|螺钉|螺柱|铆钉",       "P_FAST_SCREW"),
    (r"卡扣",                     "P_FAST_SNAP"),
]
_SPEC_HINTS = [
    (r"注塑",                     "P_INJ_S"),
    (r"CNC|车削|铣削",            "P_CNC_T"),
    (r"压铸",                     "P_DIE_CAST"),
    (r"钣金|冲压",                "P_STAMP"),
    (r"镀彩锌|彩锌",              "P_PLATE_ZN"),
    (r"镀镍|镀金",                "P_PLATE_NI"),
    (r"PCBA组件|主板.*组件",      "P_SMT"),       # 组件级才算 P_SMT（避免 PCBA 名字重复触发）
    (r"PCB(?!A)",                "P_PCB_2L"),
    (r"硅胶",                     "P_SIL_COMP"),
    (r"泡棉|EVA",                 "P_SIL_FOAM"),
    (r"线束|连接线",              "P_WIRE"),
]


def _identify_process(name: str, spec: str) -> str | None:
    # 先按名称识别成品标件（避免被 spec 中的工艺关键词误判）
    for pat, pid in _NAME_FIRST_HINTS:
        if re.search(pat, name):
            return pid
    blob = f"{name} {spec}"
    for pat, pid in _SPEC_HINTS:
        if re.search(pat, blob):
            return pid
    return None


def _process_unit_cost(process_id: str) -> float:
    rows = query_processes(process_id=process_id)
    if not rows:
        return 0.0
    r = rows[0]
    try:
        cycle = float(r.get("typical_cycle_sec") or 0)
        rate  = float(r.get("hourly_rate_cny") or 0)
        scrap = float(r.get("scrap_rate_pct") or 0)
    except ValueError:
        return 0.0
    if cycle <= 0 or rate <= 0:
        return 0.0
    base = cycle * rate / 3600
    return base / max(1 - scrap / 100, 0.5)  # 摊到良品


def _mold_unit_cost(spec: str) -> tuple[float, str]:
    """从 spec 字符串里抓"模号:XXX"并查库摊销。BOM 多数件不写模号，此时回退到 _default_mold_cost_by_process()。"""
    m = _MOLD_RE.search(spec or "")
    if not m:
        return 0.0, ""
    mid = m.group(1)
    rows = query_molds(mold_id=mid)
    if not rows:
        return 0.0, mid
    try:
        return float(rows[0].get("unit_amortization_cny") or 0), mid
    except ValueError:
        return 0.0, mid


# 按工艺默认模具摊销 (元/件) — 行业中位估算
# 当 spec 没写"模号:XXX"或库未命中时，按工艺类型给一个真实中位值
# 标定参照（扫地机实际）：
#   小精密齿轮模 6-8w / 800k 件 → 0.08-0.10
#   小结构件模  10w  / 500k 件 → 0.20
#   中件模     20w  / 400k 件 → 0.50
#   大件外壳模 35w  / 300k 件 → 1.20  (面壳/底盘/底壳/基站外壳)
#   共模 1+1   15w  / 500k×2 件 → 0.15
_DEFAULT_MOLD_COST = {
    "P_INJ_S":      0.10,   # 小件注塑 (< 50g)
    "P_INJ_M":      0.50,   # 中件注塑 (50~300g)
    "P_INJ_L":      1.20,   # 大件注塑 (> 300g)，外壳类
    "P_INJ_DOUBLE": 0.15,   # 共模 1+1 (左右件/上下件)
    "P_SIL_COMP":   0.05,   # 硅胶模压模
    "P_SIL_FOAM":   0.01,   # 模切刀模
    "P_STAMP":      0.03,   # 冲压钣金模具
    "P_DIE_CAST":   0.80,   # 压铸模 (Al/Zn 合金件)
    "P_CNC_T":      0.0,    # CNC 无模具（计入 tooling 刀具折旧）
    "P_CNC_M":      0.0,
    "P_PCB_2L":     0.0,    # PCB 无模具 (SMT 钢网在 tooling)
    "P_PCB_4L":     0.0,
}


def _default_mold_cost_by_process(process_id: str | None) -> float:
    if not process_id:
        return 0.0
    return _DEFAULT_MOLD_COST.get(process_id, 0.0)


# 按工艺默认材料成本 (元/件) — 当 BOM 不给重量/几何尺寸时的回退基线
# 标定参照：常见塑料 ~10 元/kg, 金属 ~20 元/kg, 硅胶 ~30 元/kg
_DEFAULT_MATERIAL_COST = {
    "P_INJ_S":       0.5,   # 50g 注塑件 × 10 元/kg
    "P_INJ_M":       2.5,   # 250g
    "P_INJ_L":       7.0,   # 700g 大件外壳
    "P_INJ_DOUBLE":  1.5,   # 共模 平均件重
    "P_SIL_COMP":    0.3,   # 10g 硅胶 × 30 元/kg
    "P_SIL_FOAM":    0.2,   # EVA / 泡棉小片
    "P_CNC_T":       1.0,   # 不锈钢小轴
    "P_CNC_M":       3.0,   # 金属结构件
    "P_DIE_CAST":    4.0,   # 铝锌合金件 ~200g × 20 元/kg
    "P_STAMP":       0.8,   # 钣金小件
    "P_WIRE":        1.5,   # 线材 + 端子 + 护套
    "P_PCB_2L":      1.0,   # 小 PCB 板基材
    "P_PCB_4L":      2.5,
    # 装配类无独立材料 (材料已计入被装配件)
    "P_PLATE_ZN":    0.0, "P_PLATE_NI": 0.0,
    "P_FAST_SCREW":  0.0, "P_FAST_SNAP": 0.0, "P_BOND": 0.0, "P_WELD_SOLDER": 0.0,
    "P_SMT":         0.0, "P_DIP": 0.0,
}


def _default_material_cost(process_id: str | None) -> float:
    if not process_id:
        return 0.0
    return _DEFAULT_MATERIAL_COST.get(process_id, 0.0)


def _tooling_unit_cost(process_id: str | None) -> float:
    if not process_id:
        return 0.0
    rows = query_tooling(bound_process=process_id)
    return sum(
        float(r.get("unit_depreciation_cny") or 0) for r in rows
    )


def _row_qty(row: dict) -> int:
    try:
        return max(int(float(row.get("qty") or 1)), 1)
    except (ValueError, TypeError):
        return 1


# Batch-级 tooling (按板/按 PCBA 计，不按板上元件数计)
_BATCH_PROCESSES = {"P_SMT", "P_PCB_2L", "P_PCB_4L", "P_DIP"}


def aggregate_should_cost(
    leaf: dict, current_price: float,
) -> dict:
    """聚合 leaf + 其 _descendants (L3/L4/L5 子件) 的 Should Cost 组件。

    Should Cost = 材料 + 加工 + 模具摊销 + 工具折旧 + 12% 合理利润
    五要素全部从工艺基线 + 默认值算出，**不再用 current_price 反推 implied_material**——
    保证 Should Cost 独立于 lib 查价，gap% 反映真实谈判空间。

    工艺/模具/材料按"件内份数"累加；
    Batch-级 tooling (SMT 钢网 / PCBA 治具) 在同一 leaf 内仅算一次。
    """
    rows = [leaf] + list(leaf.get("_descendants", []))
    process_cost = mold_cost = tooling_cost = material_cost = 0.0
    pids: list[str] = []
    mids: list[str] = []
    hit_count = 0
    seen_batch_tooling: set[str] = set()

    for r in rows:
        q = _row_qty(r)
        pid = _identify_process(r.get("name", ""), r.get("spec", ""))
        if pid:
            process_cost += _process_unit_cost(pid) * q
            material_cost += _default_material_cost(pid) * q
            # 批处理工艺的 tooling 在 leaf 内仅算一次
            if pid in _BATCH_PROCESSES:
                if pid not in seen_batch_tooling:
                    seen_batch_tooling.add(pid)
                    tooling_cost += _tooling_unit_cost(pid)
            else:
                tooling_cost += _tooling_unit_cost(pid) * q
            pids.append(pid)
            hit_count += 1
        # 模具摊销：① 优先从 spec 字符串"模号:XXX"查 molds.csv  ② 回退到按工艺默认摊销
        mc, mid = _mold_unit_cost(r.get("spec", ""))
        if mid and mc:
            mids.append(mid)
            mold_cost += mc * q
            hit_count += 1
        elif pid and pid in _DEFAULT_MOLD_COST:
            default_mc = _default_mold_cost_by_process(pid)
            if default_mc > 0:
                mold_cost += default_mc * q
                mids.append(f"DEFAULT({pid})")
                hit_count += 1

    sub_total = material_cost + process_cost + mold_cost + tooling_cost
    if sub_total == 0:
        return {
            "should_cost":      0.0, "covered": False,
            "process_ids":      pids, "mold_ids": mids,
            "process_cost":     0, "mold_cost": 0, "tooling_cost": 0,
            "profit":           0, "material_cost": 0,
            "descendant_hits":  hit_count,
            "descendant_count": len(rows) - 1,
        }

    profit = sub_total * 0.12
    should_cost = sub_total + profit  # 不再用 current_price 反推；material 已含在 sub_total
    return {
        "should_cost":      round(should_cost, 3),
        "covered":          True,
        "process_ids":      pids,
        "mold_ids":         mids,
        "material_cost":    round(material_cost, 3),
        "process_cost":     round(process_cost, 3),
        "mold_cost":        round(mold_cost, 3),
        "tooling_cost":     round(tooling_cost, 3),
        "profit":           round(profit, 3),
        "descendant_hits":  hit_count,
        "descendant_count": len(rows) - 1,
    }


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
            # 收集所有层级更深的后代行 (L3/L4/L5)，供 Should Cost 递归聚合用
            descendants = []
            for j in range(i + 1, len(parsed)):
                if parsed[j]["level"] <= lvl:
                    break
                descendants.append(parsed[j])
            row["_descendants"] = descendants
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

        # 包材已移出 7 桶框架（归一级"仓储物流成本"），不归桶也不计 unclassified
        if re.search(
            r"包材|包装|外箱|彩箱|说明书|保护袋|保护膜|保护套|"
            r"中托|上托|下托|纸托|斜坡垫|气泡膜|干燥剂|"
            r"PET.*胶带|固定胶带|条纹.*胶带",
            name,
        ):
            continue

        # 辅料检测
        if is_aux(name):
            unit_price = aux_price(name, spec)
            try:
                qty = max(1, int(float(row["qty"] or 1)))
            except (ValueError, TypeError):
                qty = 1
            line_cost = unit_price * qty
            # 辅料归入 structure_cmf — 也算 Should Cost (主要命中螺丝/卡扣类)
            sc = aggregate_should_cost(row, unit_price)
            bucket_cost["structure_cmf"] += line_cost
            bucket_items["structure_cmf"].append({
                "name": name, "spec": spec, "qty": qty,
                "unit_price": unit_price, "line_cost": line_cost,
                "src": "aux", "sourcing": sourcing,
                "should_cost":      sc["should_cost"],
                "should_cost_line": sc["should_cost"] if sc["covered"] else 0,
                "sc_covered":       sc["covered"],
                "process_ids":      sc["process_ids"],
                "mold_ids":         sc["mold_ids"],
                "descendant_hits":  sc["descendant_hits"],
                "descendant_count": sc["descendant_count"],
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
        sc = aggregate_should_cost(row, unit_price)
        bucket_cost[bucket] += line_cost
        bucket_items[bucket].append({
            "name": name, "spec": spec[:40] if spec else "",
            "qty": qty, "unit_price": unit_price,
            "line_cost": line_cost, "src": src,
            "sourcing": sourcing,
            "should_cost":      sc["should_cost"],
            "should_cost_line": sc["should_cost"] * qty if sc["covered"] else 0,
            "sc_covered":       sc["covered"],
            "process_ids":      sc["process_ids"],
            "mold_ids":         sc["mold_ids"],
            "descendant_hits":  sc["descendant_hits"],
            "descendant_count": sc["descendant_count"],
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

    # ── Should Cost 对比 (新) ────────────────────────────────────────
    print(f"\n{'─'*60}")
    print("  Should Cost vs 估算价  (递归 L3+ 子件 → process/mold/tooling)")
    print(f"{'─'*60}")
    print(f"  {'桶':<20} {'估算价':>8} {'Should':>8} {'gap%':>6} {'覆盖':>6} {'子件命中':>10}")
    print(f"  {'-'*66}")
    total_est = total_sc = total_covered = total_items = 0
    total_hits = total_descendants = 0
    for bkt, name_cn in BUCKETS:
        items = bucket_items.get(bkt, [])
        if not items:
            continue
        est = sum(it["line_cost"] for it in items)
        sc  = sum(it["should_cost_line"] for it in items)
        cov = sum(1 for it in items if it["sc_covered"])
        hits = sum(it.get("descendant_hits", 0) for it in items)
        desc = sum(it.get("descendant_count", 0) for it in items)
        cov_pct = cov / len(items) * 100 if items else 0
        if sc == 0:
            # 桶内无任何件能命中 process/mold/tooling（典型如能源桶的锂电池——
            # 已是成品模块，不适合 4 要素 Should Cost 模型）
            hit_str = f"{hits}/{desc}" if desc else "—"
            print(f"  {name_cn:<20} {est:>8.1f} {'—':>8} {'—':>6} {cov_pct:>5.0f}% {hit_str:>10}  (成品模块/未覆盖)")
            total_items += len(items)
            continue
        gap = (est - sc) / sc * 100 if sc else 0
        flag = " ⚠虚高" if gap > 25 else (" 💡欠估" if gap < -25 else "")
        hit_str = f"{hits}/{desc}" if desc else "—"
        print(f"  {name_cn:<20} {est:>8.1f} {sc:>8.1f} {gap:>5.0f}% {cov_pct:>5.0f}% {hit_str:>10}{flag}")
        total_est += est; total_sc += sc; total_covered += cov; total_items += len(items)
        total_hits += hits; total_descendants += desc
    if total_sc:
        gap = (total_est - total_sc) / total_sc * 100
        hit_str = f"{total_hits}/{total_descendants}"
        print(f"  {'-'*66}")
        print(f"  {'合计 (仅覆盖件)':<20} {total_est:>8.1f} {total_sc:>8.1f} {gap:>5.0f}% "
              f"{total_covered}/{total_items}件  L3+子件命中 {hit_str}")

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
