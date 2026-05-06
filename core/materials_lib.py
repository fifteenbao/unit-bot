"""
materials_lib — 材料数据库接入层

从 data/lib/materials.csv 加载材料单价，
从 data/lib/suppliers.csv 加载供应商信息，
为 structure_cmf 桶提供原材料成本分解（material_breakdown）。

消费者：
  scripts/gen_teardown.py  → stage4_aggregate_audit 的 structure_cmf 明细
  agent.py                 → query_materials / query_suppliers 工具
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

_LIB_PATH = Path(__file__).parent.parent / "data" / "lib" / "materials.csv"
_SUPPLIER_PATH = Path(__file__).parent.parent / "data" / "lib" / "suppliers.csv"


class MaterialRecord(NamedTuple):
    material_id: str
    name: str
    name_en: str
    mat_type: str
    grade: str
    density_g_cm3: float      # g/cm³，0 表示不适用（织物、涂料等）
    price_unit: str           # 元/kg, 元/m², 元/m, 元/片
    price_min: float
    price_max: float
    price_mid: float          # 中间价，供估算使用
    bom_bucket: str           # 逗号分隔，可覆盖多桶
    typical_application: str
    note: str


@lru_cache(maxsize=1)
def load_materials() -> dict[str, MaterialRecord]:
    """加载 materials.csv，以 material_id 为 key 返回字典。"""
    if not _LIB_PATH.exists():
        return {}
    result: dict[str, MaterialRecord] = {}
    with _LIB_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                pmin = float(row["price_min"])
                pmax = float(row["price_max"])
                result[row["material_id"]] = MaterialRecord(
                    material_id=row["material_id"],
                    name=row["name"],
                    name_en=row["name_en"],
                    mat_type=row["type"],
                    grade=row["grade"],
                    density_g_cm3=float(row["density_g_cm3"]) if row.get("density_g_cm3") else 0.0,
                    price_unit=row["price_unit"],
                    price_min=pmin,
                    price_max=pmax,
                    price_mid=round((pmin + pmax) / 2, 2),
                    bom_bucket=row.get("bom_bucket", ""),
                    typical_application=row.get("typical_application", ""),
                    note=row.get("note", ""),
                )
            except (ValueError, KeyError):
                continue
    return result


# ── structure_cmf 材料组合表 ──────────────────────────────────────
# 来源：行业拆机经验 + 用户提供的成本占比区间
# pct_lo / pct_hi：该材料原材料成本占 structure_cmf 桶总成本的比例
# 注意：这里统计的是原材料成本占比，不含注塑/涂装等加工费
# ──────────────────────────────────────────────────────────────────
STRUCTURE_CMF_MATERIAL_MIX: list[tuple[str, str, str, float, float]] = [
    # (material_id,        显示名,          用途,                  pct_lo, pct_hi)
    ("mat-abs-injection",  "ABS 工程塑料",  "主机外壳、尘盒",        0.20,   0.25),
    ("mat-pc-injection",   "PC 聚碳酸酯",   "透明尘盒、传感器保护罩", 0.06,  0.10),
    ("mat-al6061-sheet",   "铝合金支架",    "主板支架、电池支架",     0.04,   0.06),
    ("mat-sus304-sheet",   "不锈钢件",      "驱动轴、齿轮箱",        0.02,   0.04),
    ("mat-tpu",            "TPU / 硅胶",    "滚轮、边刷、密封圈",    0.02,   0.04),
]

# 原材料成本占 structure_cmf 总成本的比例（上述5项之和的中值）
_MAT_PCT_MID = sum((lo + hi) / 2 for _, _, _, lo, hi in STRUCTURE_CMF_MATERIAL_MIX)
# 加工成本（注塑 + 涂装 + 表面处理 + 组装）占比
_PROCESS_PCT_MID = 1.0 - _MAT_PCT_MID


def structure_cmf_material_breakdown(bucket_cost: float) -> dict:
    """
    给定 structure_cmf 桶总成本（元），返回材料成本分解。

    返回 dict：
      items       — 每种材料的 {name, application, pct_lo, pct_hi, cost_lo, cost_hi, cost_mid,
                                price_unit, price_mid (材料库单价), mat_id}
      mat_total_mid   — 原材料小计（中值）
      process_cost    — 加工费估算（注塑/涂装/表面处理）
      mat_pct_mid     — 原材料占 structure_cmf 总成本比例（中值）
      process_pct_mid — 加工费占比
      note        — 说明文字
    """
    mat_db = load_materials()
    items: list[dict] = []

    for mat_id, display_name, application, pct_lo, pct_hi in STRUCTURE_CMF_MATERIAL_MIX:
        cost_lo  = round(bucket_cost * pct_lo, 2)
        cost_hi  = round(bucket_cost * pct_hi, 2)
        cost_mid = round(bucket_cost * (pct_lo + pct_hi) / 2, 2)
        rec = mat_db.get(mat_id)
        items.append({
            "mat_id":       mat_id,
            "name":         display_name,
            "application":  application,
            "pct_lo":       pct_lo,
            "pct_hi":       pct_hi,
            "cost_lo":      cost_lo,
            "cost_hi":      cost_hi,
            "cost_mid":     cost_mid,
            "price_unit":   rec.price_unit if rec else "—",
            "lib_price_mid": rec.price_mid if rec else None,
        })

    mat_total_mid  = round(sum(it["cost_mid"] for it in items), 2)
    process_cost   = round(bucket_cost - mat_total_mid, 2)
    mat_pct_mid    = round(mat_total_mid / bucket_cost * 100, 1) if bucket_cost else 0.0
    process_pct    = round(process_cost  / bucket_cost * 100, 1) if bucket_cost else 0.0

    return {
        "items":           items,
        "mat_total_mid":   mat_total_mid,
        "process_cost":    process_cost,
        "mat_pct_mid":     mat_pct_mid,
        "process_pct_mid": process_pct,
        "note":            "原材料占比基于行业拆机经验估算；加工费含注塑/涂装/表面处理",
    }


class SupplierRecord(NamedTuple):
    supplier_id: str
    name: str
    name_en: str
    sup_type: str       # 芯片原厂 / 模组厂 / 电机厂 / 电池厂 / 组装厂 / 注塑厂
    category: str       # bom_bucket 关键词，逗号分隔
    region: str
    tier: str           # 一线 / 二线 / 三线
    typical_parts: str
    moq_note: str
    payment_terms: str
    website: str


@lru_cache(maxsize=1)
def load_suppliers() -> dict[str, SupplierRecord]:
    """加载 suppliers.csv，以 supplier_id 为 key 返回字典。"""
    if not _SUPPLIER_PATH.exists():
        return {}
    result: dict[str, SupplierRecord] = {}
    with _SUPPLIER_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = row.get("supplier_id", "").strip()
            if not sid:
                continue
            result[sid] = SupplierRecord(
                supplier_id=sid,
                name=row.get("name", ""),
                name_en=row.get("name_en", ""),
                sup_type=row.get("type", ""),
                category=row.get("category", ""),
                region=row.get("region", ""),
                tier=row.get("tier", ""),
                typical_parts=row.get("typical_parts", ""),
                moq_note=row.get("moq_note", ""),
                payment_terms=row.get("payment_terms", ""),
                website=row.get("website", ""),
            )
    return result


def query_materials(
    keyword: str | None = None,
    mat_type: str | None = None,
    bom_bucket: str | None = None,
) -> list[dict]:
    """
    查询材料库，支持按关键词/材料类型/BOM桶过滤。
    返回 list[dict]，每项包含完整 MaterialRecord 字段 + price_mid。
    """
    db = load_materials()
    results = []
    for rec in db.values():
        if mat_type and mat_type.lower() not in rec.mat_type.lower():
            continue
        if bom_bucket and bom_bucket not in rec.bom_bucket:
            continue
        if keyword:
            kw = keyword.lower()
            searchable = (rec.name + rec.name_en + rec.typical_application + rec.note).lower()
            if kw not in searchable and kw not in rec.material_id.lower():
                continue
        results.append({
            "material_id":       rec.material_id,
            "name":              rec.name,
            "name_en":           rec.name_en,
            "type":              rec.mat_type,
            "grade":             rec.grade,
            "density_g_cm3":     rec.density_g_cm3,
            "price_unit":        rec.price_unit,
            "price_min":         rec.price_min,
            "price_max":         rec.price_max,
            "price_mid":         rec.price_mid,
            "bom_bucket":        rec.bom_bucket,
            "typical_application": rec.typical_application,
            "note":              rec.note,
        })
    return results


def query_suppliers(
    keyword: str | None = None,
    category: str | None = None,
    tier: str | None = None,
    region: str | None = None,
) -> list[dict]:
    """
    查询供应商库，支持按关键词/BOM桶分类/档次/地区过滤。
    返回 list[dict]，每项包含完整 SupplierRecord 字段。
    """
    db = load_suppliers()
    results = []
    for rec in db.values():
        if tier and tier not in rec.tier:
            continue
        if region and region.lower() not in rec.region.lower():
            continue
        if category and category not in rec.category:
            continue
        if keyword:
            kw = keyword.lower()
            searchable = (rec.name + rec.name_en + rec.typical_parts + rec.sup_type).lower()
            if kw not in searchable and kw not in rec.supplier_id.lower():
                continue
        results.append({
            "supplier_id":   rec.supplier_id,
            "name":          rec.name,
            "name_en":       rec.name_en,
            "type":          rec.sup_type,
            "category":      rec.category,
            "region":        rec.region,
            "tier":          rec.tier,
            "typical_parts": rec.typical_parts,
            "moq_note":      rec.moq_note,
            "payment_terms": rec.payment_terms,
            "website":       rec.website,
        })
    return results


def print_structure_cmf_breakdown(bucket_cost: float, indent: int = 4) -> None:
    """将 structure_cmf 材料分解以对齐格式打印到 stdout。"""
    bd = structure_cmf_material_breakdown(bucket_cost)
    pad = " " * indent
    print(f"{pad}┌─ structure_cmf 材料分解（桶合计 ¥{bucket_cost:.0f}）")
    print(f"{pad}│  {'材料':14s}  {'用途':18s}  {'成本区间':>14s}  {'中值':>8s}  {'库单价':>10s}")
    print(f"{pad}│  {'─'*70}")
    for it in bd["items"]:
        lib_price = f"¥{it['lib_price_mid']:.0f}/{it['price_unit'].split('/')[-1]}" if it["lib_price_mid"] else "—"
        cost_range = f"¥{it['cost_lo']:.1f}~{it['cost_hi']:.1f}"
        print(f"{pad}│  {it['name']:14s}  {it['application']:18s}  "
              f"{cost_range:>14s}  ¥{it['cost_mid']:>6.1f}  {lib_price:>10s}")
    print(f"{pad}│  {'─'*70}")
    print(f"{pad}│  {'原材料小计':14s}  {'':18s}  {'':14s}  ¥{bd['mat_total_mid']:>6.1f}  "
          f"({bd['mat_pct_mid']:.0f}%)")
    print(f"{pad}│  {'注塑/涂装/加工':14s}  {'':18s}  {'':14s}  ¥{bd['process_cost']:>6.1f}  "
          f"({bd['process_pct_mid']:.0f}%)")
    print(f"{pad}└─ 说明：{bd['note']}")
