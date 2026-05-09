#!/usr/bin/env python3
"""
扫地机器人 BOM 成本分析 & 技术选型 Agent
支持：自动网络调研补全新产品 / 拆机BOM对比 / 选型分析
用法: python agent.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from core.components_lib import (
    CATEGORY_NAMES,
    TIER_NAMES,
    delete_component,
    get_component,
    init_standard_library,
    list_components,
    upsert_component,
)
from core.db import (
    delete_product,
    list_products,
    load_db,
    migrate_from_old_specs,
    update_completeness,
    upsert_product,
)

console = Console()

OLD_SPECS = Path(__file__).parent / "data" / "products" / "product_specs.json"

# ─── 启动时迁移旧数据（幂等） ──────────────────────────────────
def _ensure_migrated() -> None:
    from core.db import DB_FILE
    if not DB_FILE.exists() and OLD_SPECS.exists():
        n = migrate_from_old_specs(OLD_SPECS)
        if n:
            console.print(f"[dim]已从 product_specs.json 迁移 {n} 条产品数据[/dim]")



# ═══════════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════════

# ─── 查询工具 ──────────────────────────────────────────────────

def tool_list_products(include_completeness: bool = True) -> str:
    """列出所有产品及概要（价格、越障高度、吸力、数据完整度）"""
    products = list_products()
    db = load_db()
    result = []
    for p in products:
        key = p["key"]
        entry = db.get(key, {})
        specs = entry.get("specs", {})
        bom   = entry.get("bom_cost", {})
        comp  = p.get("completeness", {})
        result.append({
            "产品key": key,
            "品牌": p["brand"],
            "型号": p["model_name"],
            "上市时间": p.get("release_date", "-"),
            "定位": p.get("market_segment", "-"),
            "零售价(元)": p["retail_price_cny"],
            "越障(cm)": specs.get("obstacle_height_cm"),
            "吸力(Pa)": specs.get("suction_power_pa"),
            "PCB成本(元)": bom.get("pcb_bom_cny"),
            "完整度": {k: v for k, v in comp.items()},
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


def tool_get_product_detail(product_key: str) -> str:
    """获取单个产品的完整信息（规格+BOM成本+电机+传感器+PCB）"""
    db = load_db()
    if product_key not in db:
        return json.dumps({"error": f"产品 '{product_key}' 不存在"}, ensure_ascii=False)
    return json.dumps(db[product_key], ensure_ascii=False, indent=2)


def tool_get_motors(product_keys: list[str] | None = None) -> str:
    """获取指定产品的电机选型（驱动轮/风机/拖布/滚刷/边刷/水泵）"""
    db = load_db()
    targets = product_keys if product_keys else list(db.keys())
    result = {}
    for k in targets:
        if k in db:
            result[k] = db[k].get("motors", [])
    return json.dumps(result, ensure_ascii=False, indent=2)


def tool_get_sensors(product_keys: list[str] | None = None) -> str:
    """获取指定产品的传感器配置"""
    db = load_db()
    targets = product_keys if product_keys else list(db.keys())
    result = {}
    for k in targets:
        if k in db:
            result[k] = db[k].get("sensors", [])
    return json.dumps(result, ensure_ascii=False, indent=2)


def tool_get_pcb_components(
    product_keys: list[str] | None = None,
    function_filter: str | None = None,
) -> str:
    """
    获取PCB芯片选型。function_filter 支持关键字过滤，如：
    CPU / MCU / WIFI / 马达驱动 / 驱动轮驱动 / 充电IC / IMU / PMIC / DCDC / 音频
    """
    db = load_db()
    targets = product_keys if product_keys else list(db.keys())
    result = {}
    for k in targets:
        if k not in db:
            continue
        items = db[k].get("pcb_components", [])
        if function_filter:
            items = [
                x for x in items
                if function_filter.lower() in (x.get("function") or "").lower()
                or function_filter.lower() in (x.get("model") or "").lower()
            ]
        result[k] = items
    return json.dumps(result, ensure_ascii=False, indent=2)


def tool_get_bom_cost(product_keys: list[str] | None = None) -> str:
    """获取BOM成本信息（PCB、电机、传感器、电池、整机估算、毛利率估算）"""
    db = load_db()
    targets = product_keys if product_keys else list(db.keys())
    result = {}
    for k in targets:
        if k not in db:
            continue
        entry = db[k]
        result[k] = {
            "零售价_cny": entry.get("retail_price_cny"),
            "bom_cost": entry.get("bom_cost", {}),
            "bom_source": entry.get("bom_cost", {}).get("bom_source"),
        }
    return json.dumps(result, ensure_ascii=False, indent=2)


def tool_search_by_spec(spec_key: str, spec_value: Any) -> str:
    """
    按技术规格筛选产品。spec_key 为 specs 下的字段名，spec_value 支持：
    - 精确值：4 / true / "超声波"
    - 范围：">= 4" / "<= 2" / "> 5000"
    常用 spec_key：obstacle_height_cm / suction_power_pa / brush_lift /
    mop_lift / lidar_type / carpet_detection / drive_wheel_type
    """
    db = load_db()
    result = []
    for key, entry in db.items():
        val = entry.get("specs", {}).get(spec_key)
        matched = False
        if isinstance(spec_value, str):
            sv = spec_value.strip()
            if sv.startswith(">="):
                try:
                    matched = val is not None and float(val) >= float(sv[2:])
                except (ValueError, TypeError):
                    pass
            elif sv.startswith("<="):
                try:
                    matched = val is not None and float(val) <= float(sv[2:])
                except (ValueError, TypeError):
                    pass
            elif sv.startswith(">"):
                try:
                    matched = val is not None and float(val) > float(sv[1:])
                except (ValueError, TypeError):
                    pass
            elif sv.startswith("<"):
                try:
                    matched = val is not None and float(val) < float(sv[1:])
                except (ValueError, TypeError):
                    pass
            else:
                matched = str(val).lower() == sv.lower()
        else:
            matched = val == spec_value

        if matched:
            result.append({
                "key": key,
                "brand": entry.get("brand"),
                "model_name": entry.get("model_name"),
                spec_key: val,
                "retail_price_cny": entry.get("retail_price_cny"),
            })
    return json.dumps(result, ensure_ascii=False, indent=2)


def tool_compare_by_spec(spec_key: str, spec_value: Any, compare_category: str) -> str:
    """
    对满足 spec_key=spec_value 的产品，横向对比某类组件。
    compare_category：motors / sensors / pcb / bom_cost / specs
    示例：越障≥4cm的产品，对比其驱动轮电机 → spec_key='obstacle_height_cm', spec_value='>=4', compare_category='motors'
    """
    matching_raw = json.loads(tool_search_by_spec(spec_key, spec_value))
    keys = [x["key"] for x in matching_raw]
    if not keys:
        return json.dumps({
            "error": f"没有找到 {spec_key}={spec_value} 的产品"
        }, ensure_ascii=False)

    if compare_category == "motors":
        data = json.loads(tool_get_motors(keys))
    elif compare_category == "sensors":
        data = json.loads(tool_get_sensors(keys))
    elif compare_category == "pcb":
        data = json.loads(tool_get_pcb_components(keys))
    elif compare_category == "bom_cost":
        data = json.loads(tool_get_bom_cost(keys))
    elif compare_category == "specs":
        db = load_db()
        data = {k: db[k].get("specs", {}) for k in keys}
    else:
        data = {}

    return json.dumps({
        "filter": f"{spec_key}={spec_value}",
        "matched_products": matching_raw,
        compare_category: data,
    }, ensure_ascii=False, indent=2)


# ─── 数据库写入工具 ────────────────────────────────────────────

def tool_save_product(product_key: str, product_data: dict) -> str:
    """
    创建或更新产品条目。product_data 可包含 brand / model_name /
    retail_price_cny / release_date / market_segment / specs / bom_cost /
    motors / sensors / pcb_components / data_sources / notes 等字段。
    字段会与已有数据深度合并，不覆盖未提及的字段。
    """
    entry = upsert_product(product_key, product_data)
    update_completeness(product_key)
    comp = entry.get("data_sources", {}).get("completeness", {})

    # 同步到飞书多维表格（未配置时静默跳过）
    try:
        from core.feishu_sync import sync_product
        sync_product(product_key, entry)
    except Exception:
        pass

    return json.dumps({
        "status": "saved",
        "key": product_key,
        "completeness": comp,
    }, ensure_ascii=False)


def tool_update_spec(product_key: str, spec_key: str, spec_value: Any) -> str:
    """更新单个规格字段，spec_key 为 specs 下的字段名"""
    db = load_db()
    if product_key not in db:
        return json.dumps({"error": f"产品 '{product_key}' 不存在，请先用 save_product 创建"}, ensure_ascii=False)
    db[product_key].setdefault("specs", {})[spec_key] = spec_value
    from core.db import save_db
    save_db(db)
    update_completeness(product_key)
    return json.dumps({"status": "ok", "key": product_key, "spec_key": spec_key, "value": spec_value}, ensure_ascii=False)


def tool_update_bom_cost(product_key: str, cost_field: str, value: Any) -> str:
    """更新单个BOM成本字段，cost_field 为 bom_cost 下的字段名"""
    db = load_db()
    if product_key not in db:
        return json.dumps({"error": f"产品 '{product_key}' 不存在"}, ensure_ascii=False)
    db[product_key].setdefault("bom_cost", {})[cost_field] = value
    from core.db import save_db
    save_db(db)
    update_completeness(product_key)
    return json.dumps({"status": "ok", "key": product_key, "cost_field": cost_field, "value": value}, ensure_ascii=False)


def tool_delete_product(product_key: str) -> str:
    """删除产品条目"""
    success = delete_product(product_key)
    return json.dumps({"status": "deleted" if success else "not_found", "key": product_key}, ensure_ascii=False)


def tool_get_missing_data(product_key: str | None = None) -> str:
    """
    列出数据不完整的产品及缺失字段。
    product_key 不传则列出所有产品的缺失情况。
    """
    db = load_db()
    targets = [product_key] if product_key else list(db.keys())
    result = []
    for k in targets:
        if k not in db:
            continue
        entry = db[k]
        specs = entry.get("specs", {})
        bom   = entry.get("bom_cost", {})
        comp  = entry.get("data_sources", {}).get("completeness", {})

        missing_specs = [
            f for f in [
                "obstacle_height_cm", "suction_power_pa", "drive_wheel_type",
                "lidar_type", "battery_capacity_mah", "battery_voltage_v",
                "mop_lift", "brush_lift", "carpet_detection",
            ]
            if specs.get(f) is None
        ]
        missing_bom = [
            f for f in ["pcb_bom_cny", "motors_cost_cny", "sensors_cost_cny", "battery_cost_cny"]
            if bom.get(f) is None
        ]
        result.append({
            "key": k,
            "completeness": comp,
            "missing_specs": missing_specs,
            "missing_bom_fields": missing_bom,
            "has_motors": bool(entry.get("motors")),
            "has_sensors": bool(entry.get("sensors")),
            "has_pcb": bool(entry.get("pcb_components")),
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


# ─── 标准件库工具 ──────────────────────────────────────────────

def tool_list_components(
    category: str | None = None,
    tier: str | None = None,
    keyword: str | None = None,
) -> str:
    """
    列出标准件库中的关键件。
    category: brain_perception / drive_motion / cleaning / dock / standard
    tier: premium / mainstream / budget
    """
    items = list_components(category=category, tier=tier, keyword=keyword)
    summary = {
        "total": len(items),
        "categories": {v: 0 for v in CATEGORY_NAMES.values()},
        "components": items,
    }
    for item in items:
        cat = item.get("category", "")
        if cat in summary["categories"]:
            summary["categories"][cat] += 1
    return json.dumps(summary, ensure_ascii=False, indent=2)


def tool_get_component(comp_id: str) -> str:
    """获取单个标准件的完整信息（规格/成本区间/供应商/专利风险/降级方案）"""
    comp = get_component(comp_id)
    if not comp:
        return json.dumps({"error": f"标准件 '{comp_id}' 不存在"}, ensure_ascii=False)
    return json.dumps(comp, ensure_ascii=False, indent=2)


def tool_save_component(comp_id: str, comp_data: dict) -> str:
    """
    新增或更新标准件。comp_data 可包含：
    name / name_en / category / subcategory / tier / specs_2026 /
    suppliers[] / bom_cost_range_cny{} / patent_risk{} / degradation{} /
    related_specs[] / notes
    """
    entry = upsert_component(comp_id, comp_data)

    # 同步到飞书多维表格（未配置时静默跳过）
    try:
        from core.feishu_sync import sync_components_lib
        sync_components_lib([entry])
    except Exception:
        pass

    return json.dumps({
        "status": "saved",
        "id": comp_id,
        "name": entry.get("name"),
        "tier": entry.get("tier"),
        "category": entry.get("category"),
    }, ensure_ascii=False)


def tool_delete_component(comp_id: str) -> str:
    """从标准件库删除一个件"""
    success = delete_component(comp_id)
    return json.dumps({"status": "deleted" if success else "not_found", "id": comp_id}, ensure_ascii=False)


def tool_match_bom_to_library(product_key: str) -> str:
    """
    将产品的电机/传感器清单与标准件库交叉比对，
    识别出哪些件是"溢价件"，哪些是"主流件"，并给出降本建议。
    """
    from core.components_lib import load_lib
    db = load_db()
    if product_key not in db:
        return json.dumps({"error": f"产品 '{product_key}' 不存在"}, ensure_ascii=False)

    entry = db[product_key]
    lib = load_lib()  # list[dict]

    # 从 teardown CSV 读取该产品的零件（按名称与标准件库模糊匹配）
    import csv as _csv
    import core.bom_loader as _bom_mod
    from core.bom_loader import TEARDOWNS_DIR, _model_key_from_file
    slug = product_key.lower().replace(" ", "")

    product_parts: list[dict] = []
    for csv_file in sorted(TEARDOWNS_DIR.glob("*.csv")):
        if _model_key_from_file(csv_file).lower().replace(" ", "") not in (slug, slug.replace("_", "")):
            continue
        with csv_file.open(encoding="utf-8-sig") as f:
            for row in _csv.DictReader(f):
                if row.get("name", "").strip():
                    product_parts.append(row)

    # 按零件名模糊匹配标准件库
    lib_by_name: dict[str, list[dict]] = {}
    for comp in lib:
        lib_by_name.setdefault(comp.get("name", ""), []).append(comp)

    matches = []
    for part in product_parts:
        part_name = part.get("name", "").strip()
        candidates = lib_by_name.get(part_name, [])
        # 同 bucket 优先
        bucket = part.get("bom_bucket", "")
        same_bucket = [c for c in candidates if c.get("bom_bucket") == bucket]
        comp = (same_bucket or candidates or [None])[0]
        if not comp:
            continue
        cost_min = comp.get("cost_min", "")
        cost_max = comp.get("cost_max", "")
        matches.append({
            "name":       part_name,
            "bom_bucket": bucket,
            "tier":       TIER_NAMES.get(comp.get("tier", ""), comp.get("tier", "")),
            "model_numbers": comp.get("model_numbers", ""),
            "bom_cost_range": f"¥{cost_min}~{cost_max}" if cost_min else "待定",
            "suppliers":  comp.get("suppliers", ""),
            "confidence": comp.get("confidence", ""),
        })

    premium_count = sum(1 for m in matches if "溢价" in m.get("tier", ""))
    budget_count  = sum(1 for m in matches if "减配" in m.get("tier", ""))

    return json.dumps({
        "product":            product_key,
        "teardown_parts":     len(product_parts),
        "matched_components": matches,
        "premium_count":      premium_count,
        "budget_count":       budget_count,
        "note": "匹配基于零件名称，无拆机数据时返回空列表。运行 generate_teardown_csv 后结果更完整。",
    }, ensure_ascii=False, indent=2)


def tool_compare_cost_benchmark(product_keys: list[str] | None = None) -> str:
    """
    将产品的 BOM 成本与标准件库的基准区间对比，
    评估各子系统成本是否处于"合理区间"、"偏高"或"偏低"。
    """
    from core.components_lib import load_lib
    db = load_db()
    targets = product_keys if product_keys else list(db.keys())
    lib = load_lib()  # list[dict]

    # 按 bom_bucket 聚合标准件库的成本基准（cost_min / cost_max 均值）
    bucket_benchmarks: dict[str, dict] = {}
    for comp in lib:
        bucket = comp.get("bom_bucket", "")
        if not bucket:
            continue
        try:
            cmin = float(comp.get("cost_min") or 0)
            cmax = float(comp.get("cost_max") or 0)
        except (ValueError, TypeError):
            continue
        if cmin == 0 and cmax == 0:
            continue
        b = bucket_benchmarks.setdefault(bucket, {"min_sum": 0.0, "max_sum": 0.0, "count": 0})
        b["min_sum"] += cmin
        b["max_sum"] += cmax
        b["count"]   += 1

    # 对比每个产品的 bom_cost 7桶字段
    BUCKET_BOM_FIELD = {
        "compute_electronics": "compute_electronics_cny",
        "perception":          "perception_cny",
        "power_motion":        "power_motion_cny",
        "cleaning":            "cleaning_cny",
        "dock_station":        "dock_station_cny",
        "energy":              "energy_cny",
        "structure_cmf":       "structure_cmf_cny",
        "mva_software":        "mva_software_cny",
    }

    result = []
    for key in targets:
        if key not in db:
            continue
        entry = db[key]
        bom = entry.get("bom_cost", {})
        item: dict = {
            "product": key,
            "retail_price_cny": entry.get("retail_price_cny"),
            "bucket_comparison": {},
        }
        for bucket, field in BUCKET_BOM_FIELD.items():
            actual = bom.get(field)
            if actual is None:
                continue
            bench = bucket_benchmarks.get(bucket, {})
            if bench and bench["min_sum"] > 0:
                if actual < bench["min_sum"] * 0.7:
                    status = "偏低（可能缺数据或减配）"
                elif actual > bench["max_sum"] * 1.3:
                    status = "偏高（溢价件或高端配置）"
                else:
                    status = "合理区间"
                bench_range = f"¥{bench['min_sum']:.0f}~{bench['max_sum']:.0f}"
            else:
                status = "无基准数据"
                bench_range = "-"
            item["bucket_comparison"][bucket] = {
                "actual_cny":      actual,
                "benchmark_range": bench_range,
                "status":          status,
            }
        result.append(item)

    return json.dumps({
        "bucket_benchmarks": {
            k: {
                "cost_range": f"¥{v['min_sum']:.0f}~{v['max_sum']:.0f}",
                "component_count": v["count"],
            }
            for k, v in bucket_benchmarks.items()
        },
        "products": result,
    }, ensure_ascii=False, indent=2)


def tool_crawl_product_specs(
    model_name: str,
    force_refresh: bool = False,
) -> str:
    """
    启动对指定产品型号的规格层网络调研任务。
    返回当前数据库状态 + 缺失字段清单 + 建议搜索关键词，
    供 Agent 调用 web_search/web_fetch 补全后写入 save_product。
    """
    db = load_db()

    # 模糊匹配已有 key
    matched_key = None
    for k in db:
        if model_name.lower().replace(" ", "") in k.lower().replace(" ", "") or \
           k.lower().replace(" ", "") in model_name.lower().replace(" ", ""):
            matched_key = k
            break

    existing: dict = {}
    completeness: dict = {}
    if matched_key and not force_refresh:
        existing = db[matched_key]
        completeness = existing.get("data_sources", {}).get("completeness", {})

    # 规格层缺失字段
    specs = existing.get("specs", {})
    missing_specs = [f for f in [
        "suction_power_pa", "obstacle_height_cm", "battery_capacity_mah",
        "battery_life_min", "lidar_type", "navigation", "mop_lift",
        "mop_lift_type", "drive_wheel_type", "self_cleaning", "hot_air_dry",
        "auto_empty", "auto_wash",
    ] if specs.get(f) is None]

    # 建议搜索词（多源分层：vacuumwars → 中关村 → 电商 → 通用）
    search_queries = [
        f"site:vacuumwars.com {model_name}",
        f"vacuumwars.com {model_name} specs suction battery",
        f"中关村在线 {model_name} 参数 规格",
        f"zol.com.cn {model_name} 扫地机器人 参数",
        f"{model_name} 京东 天猫 价格 参数",
        f"{model_name} 规格参数 吸力 续航 越障高度 电池容量",
        f"{model_name} 导航方式 雷达 传感器 避障 基站功能 上下水",
        f"{model_name} 零售价 上市时间 官方商城",
    ]

    fcc_hint = _fcc_hint(model_name)

    return json.dumps({
        "model_name":       model_name,
        "db_key":           matched_key,
        "completeness":     completeness,
        "missing_specs":    missing_specs,
        "has_bom":          bool(existing.get("bom_cost", {}).get("total_bom_cny")),
        "has_motors":       bool(existing.get("motors")),
        "has_pcb":          bool(existing.get("pcb_components")),
        "suggested_queries": search_queries,
        "fcc_hint":         fcc_hint or None,
        "instruction": (
            "按多源策略依次检索：① vacuumwars.com → ② 中关村在线 → ③ 京东/天猫电商 → ④ 通用 web_search。"
            "提取完整规格（吸力/续航/越障/导航/电池/拖布/基站功能/尺寸重量）和功能布尔值后，"
            "调用 save_product 写入数据库。bom_source 标注为 'web'。"
        ),
    }, ensure_ascii=False, indent=2)


def tool_generate_teardown_csv(
    model_name: str,
    msrp: float | None = None,
) -> str:
    """
    调用 4-Stage Pipeline 为指定机型生成拆机 BOM CSV：
    Stage 1 多源调研（FCC/MyFixGuide/知乎）→
    Stage 2 SoC 伴随件推导 →
    Stage 3 标准件库定价 + LCSC 网络补全 →
    Stage 4 7桶汇总 & 偏差告警
    输出：data/teardowns/{slug}_teardown.csv
    """
    import importlib.util, sys
    ROOT = Path(__file__).parent
    _spec = importlib.util.spec_from_file_location("gen_teardown", ROOT / "scripts" / "gen_teardown.py")
    _mod  = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)

    _lookup_msrp_from_db = _mod._lookup_msrp_from_db
    lookup_msrp_from_web = _mod.lookup_msrp_from_web
    _slug        = _mod._slug
    run_pipeline = _mod.run_pipeline
    save_csv     = _mod.save_csv
    TEARDOWN_DIR = _mod.TEARDOWN_DIR

    model = model_name
    price = msrp or _lookup_msrp_from_db(model)
    if not price:
        price = lookup_msrp_from_web(model)
    price = price or 5000.0

    slug    = _slug(model)
    csv_out = TEARDOWN_DIR / f"{slug}_teardown.csv"

    try:
        rows, audit = run_pipeline(
            model=model,
            msrp=price,
        )
        save_csv(rows, csv_out, model)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    return json.dumps({
        "status": "generated",
        "csv_path": str(csv_out),
        "rows": len(rows),
        "msrp": price,
        "total_bom_cny": audit["total_actual_cny"],
        "bom_rate_pct": round(audit["total_actual_cny"] / price * 100, 1),
        "alerts": audit["alerts"],
        "buckets": {k: v["actual_cny"] for k, v in audit["buckets"].items()},
    }, ensure_ascii=False, indent=2)


def tool_generate_bom_estimate(
    product_key: str,
    retail_price_cny: float | None = None,
    overrides: dict | None = None,
) -> str:
    """
    正向 BOM 计算：
      1. 从 teardown CSV 按 bom_bucket 汇总各桶实际成本（unit_price × qty）
      2. overrides 可覆盖任意桶
      3. 缺失桶用行业基准占比补全（基于已知桶成本反推总额）
      4. 最后用零售价计算 BOM 率和毛利率

    overrides 格式：{"compute_electronics_cny": 280, "energy_cny": 200}
    """
    db = load_db()
    if product_key not in db:
        return json.dumps({"error": f"产品 '{product_key}' 不存在"}, ensure_ascii=False)

    entry = db[product_key]
    price = retail_price_cny or entry.get("retail_price_cny")

    # 7桶定义：(field, 中文名, 行业基准占比, 主要构成)
    # 占比为 BOM 总额的百分比，用于缺失桶补全
    BUCKET_DEFS = [
        ("compute_electronics_cny", "算力与电子",    0.115, "SoC·MCU·Wi-Fi·PMIC·被动元件"),
        ("perception_cny",          "感知系统",      0.130, "LDS/dToF·结构光摄像头·IMU·超声波"),
        ("power_motion_cny",        "动力与驱动",    0.105, "吸尘风机·驱动轮电机·底盘升降"),
        ("cleaning_cny",            "清洁功能",      0.145, "拖布驱动·水泵·水箱·边刷·滚刷"),
        ("dock_station_cny",        "基站系统",      0.200, "集尘·水路·加热·基站电控·基站结构"),
        ("energy_cny",              "能源系统",      0.085, "电芯·BMS·充电IC"),
        ("structure_cmf_cny",       "整机结构CMF",   0.115, "外壳注塑·喷涂·模具摊销"),
        ("mva_software_cny",        "MVA+软件授权",  0.105, "组装人工·算法版税·OS·包材"),
    ]

    # bom_bucket CSV 字段名 → field 名映射
    BUCKET_KEY_MAP = {
        "compute_electronics": "compute_electronics_cny",
        "perception":          "perception_cny",
        "power_motion":        "power_motion_cny",
        "cleaning":            "cleaning_cny",
        "dock_station":        "dock_station_cny",
        "energy":              "energy_cny",
        "structure_cmf":       "structure_cmf_cny",
        "mva_software":        "mva_software_cny",
    }

    # ── Step 1: 从 teardown CSV 汇总各桶实际成本 ──────────────────
    from core.bom_loader import get_bom_data, _bom_cache
    import core.bom_loader as _bom_mod
    _bom_mod._bom_cache = None  # 清缓存，读最新数据

    teardown_totals: dict[str, float] = {}
    teardown_items:  dict[str, int]   = {}  # 各桶零件条数，用于置信度判断

    # 模糊匹配 teardown key
    # product_key 可能是长 key（如 "Roborock_石头自清洁扫拖机器人P20UltraPlus"）
    # teardown CSV slug 是短 model_name（如 "石头P20UltraPlus"）
    # 策略：提取 product_key 中连续的汉字+字母数字片段逐一尝试包含匹配
    import re as _re
    bom_data = get_bom_data()
    slug = product_key.lower().replace(" ", "").replace("_", "")

    def _tok(s: str) -> list[str]:
        return [t.lower() for t in _re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", s) if len(t) >= 3]

    key_tokens = _tok(product_key)

    def _score(k: str) -> int:
        k_norm = k.lower().replace(" ", "").replace("_", "")
        if k_norm == slug:
            return 100
        if k_norm in slug or slug in k_norm:
            return 80
        # 按 token 命中数打分
        return sum(1 for t in key_tokens if t in k_norm)

    matched_key = max(bom_data.keys(), key=_score, default=None)
    if matched_key and _score(matched_key) == 0:
        matched_key = None

    if matched_key:
        # 重新读原始 CSV 按 bom_bucket 汇总（bom_loader 按 section 分类，需原始数据）
        import csv as _csv
        from core.bom_loader import TEARDOWNS_DIR
        for csv_file in sorted(TEARDOWNS_DIR.glob("*.csv")):
            from core.bom_loader import _model_key_from_file
            if _model_key_from_file(csv_file).lower().replace(" ", "") != matched_key.lower().replace(" ", ""):
                continue
            with csv_file.open(encoding="utf-8-sig") as f:
                for row in _csv.DictReader(f):
                    bucket = (row.get("bom_bucket") or "").strip()
                    field  = BUCKET_KEY_MAP.get(bucket)
                    if not field:
                        continue
                    try:
                        unit_price = float(row.get("unit_price") or 0)
                        qty        = int(float(row.get("qty") or 1))
                        teardown_totals[field] = teardown_totals.get(field, 0) + unit_price * qty
                        teardown_items[field]  = teardown_items.get(field, 0) + 1
                    except (ValueError, TypeError):
                        pass

    # ── Step 2: 合并 overrides（优先级最高）────────────────────────
    known: dict[str, float] = {}
    known.update({k: v for k, v in teardown_totals.items() if v > 0})
    known.update({k: float(v) for k, v in (overrides or {}).items() if v})

    # ── Step 3: 用已知桶反推总额，补全缺失桶 ─────────────────────
    known_ratio_sum = sum(r for f, _, r, _ in BUCKET_DEFS if f in known)
    known_cost_sum  = sum(known[f] for f, _, _, _ in BUCKET_DEFS if f in known)

    if known_ratio_sum > 0:
        # 用已知桶的成本/占比推算总额
        inferred_total = known_cost_sum / known_ratio_sum
    else:
        # 无任何实测数据，回退到零售价估算（旗舰50%/中端52%/入门58%）
        if price:
            segment = (entry.get("market_segment") or "").lower()
            rate = 0.48 if ("旗舰" in segment or (price or 0) >= 4000) else \
                   0.58 if ("入门" in segment or (price or 0) < 2000) else 0.52
            inferred_total = price * rate
        else:
            inferred_total = 3000.0  # 无任何依据时的兜底值

    # ── Step 4: 组装输出表 ────────────────────────────────────────
    rows = []
    bom_patch = {}
    total_actual = 0.0

    for field, label, ratio, components in BUCKET_DEFS:
        if field in known:
            cost = known[field]
            source = "teardown" if field in teardown_totals else "override"
            items  = teardown_items.get(field, 0)
            note   = f"{items} 条零件" if items else "手动传入"
        else:
            cost   = inferred_total * ratio
            source = "estimate"
            note   = f"行业基准 {ratio*100:.0f}%"

        total_actual += cost
        bom_patch[field] = round(cost, 1)
        rows.append({
            "子系统":    label,
            "主要构成":  components,
            "成本_cny":  round(cost, 1),
            "数据来源":  source,
            "说明":      note,
        })

    # ── Step 5: 计算 BOM 率和毛利率 ──────────────────────────────
    bom_patch["total_bom_cny"] = round(total_actual, 1)
    bom_patch["bom_source"]    = "teardown" if teardown_totals else "estimate"

    if price:
        bom_rate_pct         = round(total_actual / price * 100, 1)
        gross_margin_pct     = round((1 - total_actual / price) * 100, 1)
        bom_patch["gross_margin_est_pct"] = gross_margin_pct
    else:
        bom_rate_pct     = None
        gross_margin_pct = None

    # 写回 db
    from core.db import save_db
    entry.setdefault("bom_cost", {}).update(bom_patch)
    save_db(db)
    update_completeness(product_key)

    result: dict = {
        "product":          product_key,
        "retail_price_cny": price,
        "teardown_matched": matched_key,
        "bom_table":        rows,
        "total_bom_cny":    round(total_actual, 1),
    }
    if bom_rate_pct is not None:
        result["bom_rate_pct"]      = bom_rate_pct
        result["gross_margin_pct"]  = gross_margin_pct
    if not teardown_totals:
        result["note"] = "无拆机数据，各桶成本均为行业基准估算。运行 generate_teardown_csv 后精度可大幅提升。"

    return json.dumps(result, ensure_ascii=False, indent=2)


# ─── 材料库 & 供应商查询 ────────────────────────────────────────

def tool_query_materials(
    keyword: str | None = None,
    mat_type: str | None = None,
    bom_bucket: str | None = None,
) -> str:
    """
    查询 data/lib/materials.csv 材料库。
    keyword: 在名称/用途/备注中模糊搜索
    mat_type: 工程塑料 / 弹性体 / 金属 / 滤材 / 织物 / 泡棉 / 涂料 / 复合材料
    bom_bucket: structure_cmf / cleaning / compute_electronics / dock_station / energy / power_motion / perception
    """
    from core.materials_lib import query_materials
    results = query_materials(keyword=keyword, mat_type=mat_type, bom_bucket=bom_bucket)
    return json.dumps({
        "total": len(results),
        "materials": results,
    }, ensure_ascii=False, indent=2)


def tool_query_suppliers(
    keyword: str | None = None,
    category: str | None = None,
    tier: str | None = None,
    region: str | None = None,
) -> str:
    """
    查询 data/lib/suppliers.csv 供应商库。
    keyword: 在名称/英文名/典型产品中模糊搜索
    category: compute_electronics / perception / power_motion / energy / structure_cmf / cleaning / dock_station
    tier: 一线 / 二线 / 三线
    region: 大陆 / 台湾 / 日本 / 韩国 / 欧洲 / 美国
    """
    from core.materials_lib import query_suppliers
    results = query_suppliers(keyword=keyword, category=category, tier=tier, region=region)
    return json.dumps({
        "total": len(results),
        "suppliers": results,
    }, ensure_ascii=False, indent=2)


# ─── DFMA 分析 ────────────────────────────────────────────────

def tool_dfma_analysis(
    product_key: str,
    segment: str | None = None,
    retail_price_cny: float | None = None,
) -> str:
    """
    DFMA 功能-成本矩阵分析。
    基于 7 桶 BOM 数据 + user_value_weight 计算每桶的价值/成本比，
    识别"高成本低价值"桶（优先降本）和"高价值低成本"桶（可投入）。
    输出各桶的 DFMA 抓手建议。
    """
    from core.bucket_framework import load_framework
    db = load_db()

    if product_key not in db:
        return json.dumps({"error": f"产品 '{product_key}' 不存在，请先运行 generate_bom_estimate"}, ensure_ascii=False)

    entry = db[product_key]
    price = retail_price_cny or entry.get("retail_price_cny") or 0
    bom   = entry.get("bom_cost", {})
    total_bom = bom.get("total_bom_cny", 0)

    # 自动推断档位
    if not segment:
        seg_raw = (entry.get("market_segment") or "").lower()
        if "旗舰" in seg_raw or (price and price >= 4000):
            segment = "flagship"
        elif "入门" in seg_raw or (price and price < 2000):
            segment = "entry"
        else:
            segment = "mid"

    framework = load_framework()
    buckets_def = framework.get("buckets", {})

    BUCKET_FIELD = {
        "compute_electronics": "compute_electronics_cny",
        "perception":          "perception_cny",
        "power_motion":        "power_motion_cny",
        "cleaning":            "cleaning_cny",
        "dock_station":        "dock_station_cny",
        "energy":              "energy_cny",
        "structure_cmf":       "structure_cmf_cny",
        "mva_software":        "mva_software_cny",
    }

    matrix = []
    for bucket_key, field in BUCKET_FIELD.items():
        bdef = buckets_def.get(bucket_key, {})
        cost_cny = bom.get(field)
        if cost_cny is None:
            continue

        cost_pct = round(cost_cny / total_bom * 100, 1) if total_bom else None
        industry_avg = bdef.get("industry_pct_avg", 0)
        cost_vs_bench = round(cost_pct - industry_avg, 1) if cost_pct is not None else None

        vw = bdef.get("user_value_weight", {})
        value_weight = vw.get(segment, vw.get("mid", 0.5))

        # 价值/成本比：value_weight / cost_pct_normalized
        # 归一化成本占比（相对行业均值），避免零除
        norm_cost = (cost_pct / industry_avg) if (industry_avg and cost_pct) else 1.0
        value_cost_ratio = round(value_weight / norm_cost, 2) if norm_cost else None

        # 象限判断
        high_value = value_weight >= 0.75
        high_cost  = (cost_vs_bench or 0) > 2  # 比行业均值高 2pp 以上
        if high_cost and not high_value:
            quadrant = "优先降本"
        elif high_value and not high_cost:
            quadrant = "保持投入"
        elif high_cost and high_value:
            quadrant = "溢价合理（需验证）"
        else:
            quadrant = "基准匹配"

        matrix.append({
            "桶":         bdef.get("name_cn", bucket_key),
            "bucket_key": bucket_key,
            "成本_cny":   round(cost_cny, 1),
            "成本占比_%": cost_pct,
            "行业均值_%": industry_avg,
            "偏差_pp":    cost_vs_bench,
            "用户价值权重": value_weight,
            "价值成本比":  value_cost_ratio,
            "象限":       quadrant,
            "dfma_抓手":  bdef.get("dfma_levers", []),
        })

    # 按"优先降本"排序，再按偏差降序
    quadrant_order = {"优先降本": 0, "溢价合理（需验证）": 1, "保持投入": 2, "基准匹配": 3}
    matrix.sort(key=lambda r: (quadrant_order.get(r["象限"], 9), -(r["偏差_pp"] or 0)))

    priority_buckets = [r for r in matrix if r["象限"] == "优先降本"]
    total_saving_est = sum(
        round((r["偏差_pp"] / 100) * total_bom, 0)
        for r in priority_buckets
        if r["偏差_pp"] and r["偏差_pp"] > 0
    )

    return json.dumps({
        "product":           product_key,
        "segment":           segment,
        "retail_price_cny":  price,
        "total_bom_cny":     total_bom,
        "bom_rate_pct":      round(total_bom / price * 100, 1) if price else None,
        "matrix":            matrix,
        "priority_buckets":  [r["桶"] for r in priority_buckets],
        "saving_potential_cny": total_saving_est,
        "note": (
            "价值成本比 < 0.8 → 成本偏高但用户感知低，DFMA 优先介入。"
            "价值成本比 > 1.2 → 成本偏低但用户价值高，可适当追加投入。"
        ),
    }, ensure_ascii=False, indent=2)


# ─── /cut /vs /find /framework ────────────────────────────────

def tool_cut_premium(product_key: str) -> str:
    """识别溢价件，给出替代方案和节省金额估算。"""
    from core.components_lib import load_lib
    import csv as _csv
    import core.bom_loader as _bom_mod
    from core.bom_loader import TEARDOWNS_DIR, _model_key_from_file

    lib = load_lib()
    lib_by_name: dict[str, dict] = {c.get("name", ""): c for c in lib}

    # 读取 teardown CSV
    slug = product_key.lower().replace(" ", "")
    parts: list[dict] = []
    for csv_file in sorted(TEARDOWNS_DIR.glob("*.csv")):
        if _model_key_from_file(csv_file).lower().replace(" ", "") not in (slug, slug.replace("_", "")):
            continue
        with csv_file.open(encoding="utf-8-sig") as f:
            parts = [r for r in _csv.DictReader(f) if r.get("name", "").strip()]
        break

    premium_hits = []
    total_saving = 0.0
    for part in parts:
        name = part.get("name", "").strip()
        comp = lib_by_name.get(name)
        if not comp or comp.get("tier") != "premium":
            continue
        cost_min = float(comp.get("cost_min") or 0)
        cost_max = float(comp.get("cost_max") or 0)
        current_mid = (cost_min + cost_max) / 2 if cost_min or cost_max else 0

        # 找同名 mainstream 替代件
        alt = next((c for c in lib if c.get("name") == name and c.get("tier") == "mainstream"), None)
        if not alt:
            alt = next((c for c in lib
                        if c.get("bom_bucket") == comp.get("bom_bucket") and c.get("tier") == "mainstream"
                        and c.get("name") != name), None)
        alt_min = float(alt.get("cost_min") or 0) if alt else 0
        alt_max = float(alt.get("cost_max") or 0) if alt else 0
        alt_mid = (alt_min + alt_max) / 2 if alt else 0
        saving = max(0.0, current_mid - alt_mid)
        total_saving += saving

        premium_hits.append({
            "name":          name,
            "bom_bucket":    comp.get("bom_bucket", ""),
            "current_cost":  f"¥{cost_min}~{cost_max}",
            "alt_name":      alt.get("name", "") if alt else "待定",
            "alt_cost":      f"¥{alt_min}~{alt_max}" if alt else "—",
            "saving_est":    round(saving, 1),
            "note":          comp.get("spec", ""),
        })

    if not parts:
        return json.dumps({"error": f"未找到 {product_key} 的拆机 CSV，请先运行 generate_teardown_csv"}, ensure_ascii=False)

    return json.dumps({
        "product":          product_key,
        "teardown_parts":   len(parts),
        "premium_hits":     premium_hits,
        "total_saving_est": round(total_saving, 1),
        "note":             "节省估算 = 当前溢价件中间价 − 主流替代件中间价，仅供参考",
    }, ensure_ascii=False, indent=2)


def tool_vs_compare(model_a: str, model_b: str, bucket: str | None = None) -> str:
    """两机型子系统或整机并排对标。bucket 为空则 7 桶并排，否则按该桶 typical_items 逐项对比。"""
    from core.bucket_framework import buckets_ordered, typical_items_with_qty
    import csv as _csv
    import core.bom_loader as _bom_mod
    from core.bom_loader import TEARDOWNS_DIR, _model_key_from_file

    def _load_parts(product_key: str) -> list[dict]:
        slug = product_key.lower().replace(" ", "")
        for csv_file in sorted(TEARDOWNS_DIR.glob("*.csv")):
            if _model_key_from_file(csv_file).lower().replace(" ", "") not in (slug, slug.replace("_", "")):
                continue
            with csv_file.open(encoding="utf-8-sig") as f:
                return [r for r in _csv.DictReader(f) if r.get("name", "").strip()]
        return []

    def _bucket_total(parts: list[dict], bkt: str) -> float:
        return sum(float(r.get("_line_cost") or 0) for r in parts if r.get("bom_bucket") == bkt)

    def _bucket_parts(parts: list[dict], bkt: str) -> list[str]:
        return [r.get("name", "") for r in parts if r.get("bom_bucket") == bkt]

    parts_a = _load_parts(model_a)
    parts_b = _load_parts(model_b)
    buckets = buckets_ordered()

    if bucket:
        # 单桶逐 typical_item 对比
        items = [name for name, _, _ in typical_items_with_qty(bucket)]
        rows = []
        parts_a_names = set(_bucket_parts(parts_a, bucket))
        parts_b_names = set(_bucket_parts(parts_b, bucket))
        for item in items:
            rows.append({
                "item":    item,
                model_a:   "✓" if item in parts_a_names else "—",
                model_b:   "✓" if item in parts_b_names else "—",
            })
        return json.dumps({
            "bucket": bucket,
            "models": [model_a, model_b],
            "comparison": rows,
            "bucket_cost": {
                model_a: _bucket_total(parts_a, bucket),
                model_b: _bucket_total(parts_b, bucket),
            },
        }, ensure_ascii=False, indent=2)
    else:
        # 7 桶并排
        rows = []
        for bkt, name_cn in buckets:
            rows.append({
                "桶":      name_cn,
                f"{model_a}_cost": round(_bucket_total(parts_a, bkt), 1),
                f"{model_b}_cost": round(_bucket_total(parts_b, bkt), 1),
                "差值":    round(_bucket_total(parts_a, bkt) - _bucket_total(parts_b, bkt), 1),
            })
        total_a = sum(r[f"{model_a}_cost"] for r in rows)
        total_b = sum(r[f"{model_b}_cost"] for r in rows)
        return json.dumps({
            "models": [model_a, model_b],
            "buckets": rows,
            "bom_total": {model_a: round(total_a, 1), model_b: round(total_b, 1)},
            "note": "成本来自 teardown CSV _line_cost 字段，缺 teardown 则为 0",
        }, ensure_ascii=False, indent=2)


def tool_find_parts(keyword: str, bucket: str | None = None) -> str:
    """按关键词或桶名搜索 teardown CSV + components_lib，返回匹配条目。"""
    from core.components_lib import load_lib
    import csv as _csv
    from core.bom_loader import TEARDOWNS_DIR

    lib = load_lib()
    # 搜索 components_lib
    kw = keyword.lower()
    lib_hits = [
        {"source": "lib", "id": c.get("id", ""), "name": c.get("name", ""),
         "bom_bucket": c.get("bom_bucket", ""), "tier": c.get("tier", ""),
         "cost": f"¥{c.get('cost_min','')}~{c.get('cost_max','')}",
         "spec": (c.get("spec") or "")[:60]}
        for c in lib
        if (kw in c.get("name", "").lower() or kw in (c.get("spec") or "").lower()
            or kw in c.get("bom_bucket", "").lower() or kw in c.get("id", "").lower())
        and (not bucket or c.get("bom_bucket") == bucket)
    ]

    # 搜索 teardown CSV（所有已有文件）
    teardown_hits: list[dict] = []
    for csv_file in sorted(TEARDOWNS_DIR.glob("*_teardown*.csv")):
        with csv_file.open(encoding="utf-8-sig") as f:
            for row in _csv.DictReader(f):
                name = row.get("name", "").strip()
                bkt  = row.get("bom_bucket", "").strip()
                if not name:
                    continue
                if (kw in name.lower() or kw in bkt.lower()) and (not bucket or bkt == bucket):
                    teardown_hits.append({
                        "source":     csv_file.stem,
                        "name":       name,
                        "bom_bucket": bkt,
                        "model":      row.get("model", ""),
                        "cost":       row.get("_line_cost", ""),
                        "confidence": row.get("confidence", ""),
                    })
        if len(teardown_hits) >= 50:
            break

    return json.dumps({
        "keyword":       keyword,
        "bucket_filter": bucket,
        "lib_hits":      lib_hits,
        "teardown_hits": teardown_hits[:50],
        "total":         len(lib_hits) + len(teardown_hits),
    }, ensure_ascii=False, indent=2)


def tool_export_framework() -> str:
    """导出 7 桶对账 CSV（data/lib/bom_8bucket_framework.csv），用于填价对账。"""
    import subprocess
    import sys
    script = str(ROOT / "scripts" / "export_framework_csv.py")
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True,
        cwd=str(ROOT),
    )
    if result.returncode == 0:
        out_path = str(DATA_DIR / "lib" / "bom_8bucket_framework.csv")
        return json.dumps({
            "status": "ok",
            "output_path": out_path,
            "message": result.stdout.strip() or "导出完成",
        }, ensure_ascii=False)
    return json.dumps({
        "status": "error",
        "stderr": result.stderr.strip(),
    }, ensure_ascii=False)


# ─── /plans PLANS 价值设计流程（5 个子 agent） ──────────────────

def _stage_module(stage: str):
    """按 stage key 动态加载子 agent 模块。"""
    from agents import (
        a_function, a_trim,
        l_dfa, l_dfm,
        n_fos, n_patent, n_trend,
        p_issues, p_research, p_teardown,
        s_costsystem, s_platform,
    )
    return {
        "p_research":   p_research,
        "p_teardown":   p_teardown,
        "p_issues":     p_issues,
        "l_dfa":        l_dfa,
        "l_dfm":        l_dfm,
        "a_function":   a_function,
        "a_trim":       a_trim,
        "n_fos":        n_fos,
        "n_patent":     n_patent,
        "n_trend":      n_trend,
        "s_platform":   s_platform,
        "s_costsystem": s_costsystem,
    }[stage]


# 阶段 → 命令名（去掉 stage prefix）。例：p_research → research
_STAGE_TO_COMMAND = {
    "p_research":   "research",
    "p_teardown":   "teardown",
    "p_issues":     "issues",
    "l_dfa":        "dfa",
    "l_dfm":        "dfm",
    "a_function":   "function",
    "a_trim":       "trim",
    "n_fos":        "fos",
    "n_patent":     "patent",
    "n_trend":      "trend",
    "s_platform":   "platform",
    "s_costsystem": "costsystem",
}


def _run_plans_stage(stage: str, product_key: str) -> str:
    """统一入口：跑一个 PLANS 子 agent，落 plans_db.json + md。"""
    from agents.base import filter_tools, run_subagent
    from core import plans_store

    stage_module = _stage_module(stage)

    missing = plans_store.missing_deps(product_key, stage)
    if missing:
        hint_cmds = " / ".join(f"/{_STAGE_TO_COMMAND.get(s, s)}" for s in missing)
        return json.dumps({
            "status": "blocked",
            "stage": stage,
            "product_key": product_key,
            "missing_prereqs": missing,
            "hint": f"先跑 {hint_cmds} 再回来",
        }, ensure_ascii=False)

    client, effective_tools = _make_client()
    sub_tools = filter_tools(effective_tools, stage_module.ALLOWED_TOOLS)

    console.print(f"  [dim]▶ {stage_module.STAGE_TITLE} 子 agent 启动 ({len(sub_tools)} 个工具)[/dim]")

    text, data = run_subagent(
        client=client,
        system_prompt=stage_module.SYSTEM_PROMPT,
        tools=sub_tools,
        dispatch=CLIENT_DISPATCH,
        user_input=stage_module.build_user_input(product_key),
        log=lambda m: console.print(f"    [dim]{m}[/dim]"),
    )

    if data is None:
        return json.dumps({
            "status": "error",
            "stage": stage,
            "product_key": product_key,
            "message": "子 agent 未返回有效 JSON",
            "raw_tail": text[-400:] if text else "",
        }, ensure_ascii=False)

    md_text = stage_module.render_md(product_key, data)
    md_path = plans_store.save_stage(product_key, stage, data, md_text)

    return json.dumps({
        "status": "ok",
        "stage": stage,
        "stage_title": stage_module.STAGE_TITLE,
        "product_key": product_key,
        "report_path": str(md_path),
        "summary": data.get("summary") or "",
    }, ensure_ascii=False)


# ─── 12 个 plans_run_* 工具实现（统一委托给 _run_plans_stage） ─────

def tool_plans_research(product_key: str)   -> str: return _run_plans_stage("p_research",   product_key)
def tool_plans_teardown(product_key: str)   -> str: return _run_plans_stage("p_teardown",   product_key)
def tool_plans_issues(product_key: str)     -> str: return _run_plans_stage("p_issues",     product_key)
def tool_plans_dfa(product_key: str)        -> str: return _run_plans_stage("l_dfa",        product_key)
def tool_plans_dfm(product_key: str)        -> str: return _run_plans_stage("l_dfm",        product_key)
def tool_plans_function(product_key: str)   -> str: return _run_plans_stage("a_function",   product_key)
def tool_plans_trim(product_key: str)       -> str: return _run_plans_stage("a_trim",       product_key)
def tool_plans_fos(product_key: str)        -> str: return _run_plans_stage("n_fos",        product_key)
def tool_plans_patent(product_key: str)     -> str: return _run_plans_stage("n_patent",     product_key)
def tool_plans_trend(product_key: str)      -> str: return _run_plans_stage("n_trend",      product_key)
def tool_plans_platform(product_key: str)   -> str: return _run_plans_stage("s_platform",   product_key)
def tool_plans_costsystem(product_key: str) -> str: return _run_plans_stage("s_costsystem", product_key)


def tool_plans_run_all(product_key: str, stages: list[str] | None = None) -> str:
    """串行跑 PLANS 全 12 阶段（P→L→A→N→S），默认全部，可指定子集。

    依赖关系会被自动尊重：blocked 阶段被跳过，但不算 error。
    """
    from core import plans_store

    plan_order = stages or list(plans_store.STAGES)

    results = []
    for s in plan_order:
        if s not in plans_store.STAGES:
            results.append({"stage": s, "status": "error", "message": f"unknown stage {s}"})
            continue
        raw = _run_plans_stage(s, product_key)
        results.append(json.loads(raw))
        if results[-1].get("status") not in ("ok", "blocked"):
            break  # error 则停

    overview_path = None
    if any(r.get("status") == "ok" for r in results):
        overview_path = str(plans_store.render_overview(product_key))

    return json.dumps({
        "product_key": product_key,
        "stage_results": results,
        "overview_path": overview_path,
    }, ensure_ascii=False)


def tool_plans_overview(product_key: str) -> str:
    """重新生成 overview.md（合并所有已完成阶段）。"""
    from core import plans_store
    try:
        path = plans_store.render_overview(product_key)
    except FileNotFoundError as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
    return json.dumps({
        "status": "ok",
        "product_key": product_key,
        "overview_path": str(path),
    }, ensure_ascii=False)


def tool_plans_status(product_key: str) -> str:
    """查看某机型已完成哪些 PLANS 阶段。"""
    from core import plans_store

    stages = plans_store.list_stages(product_key)
    out = {
        "product_key": product_key,
        "stages": {},
    }
    for s in plans_store.STAGES:
        info = stages.get(s)
        out["stages"][s] = {
            "done":        info is not None,
            "ran_at":      info.get("ran_at") if info else None,
            "report_path": info.get("report_path") if info else None,
        }
    return json.dumps(out, ensure_ascii=False)


# ─── FCC 辅助（PCB 芯片识别） ──────────────────────────────────

BRAND_FCC_CODE: dict[str, str] = {
    "石头":     "2AN2O",
    "roborock": "2AN2O",
    "云鲸":     "2ARZZ",
    "narwal":   "2ARZZ",
    "追觅":     "2AX54",
    "dreame":   "2AX54",
    "科沃斯":   "2A6HE",
    "ecovacs":  "2A6HE",
}


def _fcc_hint(model_name: str) -> str:
    low = model_name.lower()
    for keyword, code in BRAND_FCC_CODE.items():
        if keyword in low:
            # 尝试查海外型号（FCC 以海外型号申报）
            brand_map = {
                "石头": "Roborock", "roborock": "Roborock",
                "云鲸": "Narwal",   "narwal":   "Narwal",
                "追觅": "Dreame",   "dreame":   "Dreame",
                "科沃斯": "Ecovacs","ecovacs":  "Ecovacs",
            }
            brand = brand_map.get(keyword)
            global_name = None
            try:
                from core.model_aliases import cn_to_global, find_alias
                global_name = cn_to_global(model_name, brand)
                if not global_name:
                    hits = find_alias(model_name, brand, top_k=1)
                    if hits and hits[0].score >= 0.5:
                        global_name = hits[0].global_model
            except Exception:
                pass

            search_name = global_name or model_name
            return (
                f"FCC grantee code: {code}\n"
                f"- 设备列表: https://fccid.io/{code}\n"
                f"- 建议搜索型号: 「{search_name}」"
                + (f"（国内型号 {model_name} 的海外对应款）" if global_name else "（未找到海外对应型号，用原名模糊搜索）")
                + "\n- 进入最相近型号，用 web_fetch 抓取 Internal Photos 和 Block Diagram\n"
                f"- 从照片识别 PCB 芯片型号（SoC/MCU/Wi-Fi/PMIC），从框图提取系统架构"
            )
    return ""


# ═══════════════════════════════════════════════════════════════
#  工具注册
# ═══════════════════════════════════════════════════════════════

# 内置 web_search + web_fetch（server-side，Anthropic 执行）
SERVER_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search"},
    {"type": "web_fetch_20260209",  "name": "web_fetch"},
]

CLIENT_TOOLS: list[dict] = [
    {
        "name": "list_products",
        "description": "列出数据库中所有产品型号及概要（价格、越障、吸力、数据完整度）",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_completeness": {"type": "boolean", "default": True}
            },
        },
    },
    {
        "name": "get_product_detail",
        "description": "获取单个产品的完整信息（规格/BOM成本/电机/传感器/PCB）",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_key": {"type": "string", "description": "产品唯一key，如 '科沃斯X2pro'"},
            },
            "required": ["product_key"],
        },
    },
    {
        "name": "get_motors",
        "description": "获取产品电机选型（驱动轮/风机/拖布/滚刷/边刷/水泵）",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_keys": {"type": "array", "items": {"type": "string"}}
            },
        },
    },
    {
        "name": "get_sensors",
        "description": "获取产品传感器配置（激光雷达/摄像头/碰撞/地毯识别等）",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_keys": {"type": "array", "items": {"type": "string"}}
            },
        },
    },
    {
        "name": "get_pcb_components",
        "description": (
            "获取PCB芯片选型。function_filter 关键字：CPU / MCU / WIFI / "
            "马达驱动 / 驱动轮驱动 / 充电IC / IMU / PMIC / DCDC / 音频"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_keys": {"type": "array", "items": {"type": "string"}},
                "function_filter": {"type": "string"},
            },
        },
    },
    {
        "name": "get_bom_cost",
        "description": "获取BOM成本信息（PCB、电机、传感器、电池、整机估算、毛利率估算）",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_keys": {"type": "array", "items": {"type": "string"}}
            },
        },
    },
    {
        "name": "search_by_spec",
        "description": (
            "按技术规格筛选产品。spec_value 支持范围：'>= 4' / '<= 2' / '> 5000'。\n"
            "常用 spec_key：obstacle_height_cm / suction_power_pa / brush_lift / "
            "mop_lift / lidar_type / carpet_detection / drive_wheel_type"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "spec_key":   {"type": "string"},
                "spec_value": {"description": "精确值或范围字符串"},
            },
            "required": ["spec_key", "spec_value"],
        },
    },
    {
        "name": "compare_by_spec",
        "description": (
            "对满足某规格条件的产品，横向对比指定类别组件。\n"
            "compare_category：motors / sensors / pcb / bom_cost / specs\n"
            "示例：越障>=4cm的产品驱动轮电机对比"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "spec_key":          {"type": "string"},
                "spec_value":        {"description": "筛选条件值"},
                "compare_category":  {
                    "type": "string",
                    "enum": ["motors", "sensors", "pcb", "bom_cost", "specs"],
                },
            },
            "required": ["spec_key", "spec_value", "compare_category"],
        },
    },
    {
        "name": "save_product",
        "description": (
            "创建或更新产品条目（深度合并，不覆盖已有数据）。\n"
            "product_data 可包含：brand / model_name / retail_price_cny / "
            "release_date / market_segment / product_page_url / specs{} / "
            "bom_cost{} / motors[] / sensors[] / pcb_components[] / notes"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_key":  {"type": "string", "description": "唯一key，建议格式：品牌+型号，如 '追觅X40Ultra'"},
                "product_data": {"type": "object", "description": "产品数据字典"},
            },
            "required": ["product_key", "product_data"],
        },
    },
    {
        "name": "update_spec",
        "description": "更新单个规格字段（specs 下的字段）",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_key": {"type": "string"},
                "spec_key":    {"type": "string"},
                "spec_value":  {},
            },
            "required": ["product_key", "spec_key", "spec_value"],
        },
    },
    {
        "name": "update_bom_cost",
        "description": "更新单个BOM成本字段（bom_cost 下的字段）",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_key": {"type": "string"},
                "cost_field":  {"type": "string"},
                "value":       {},
            },
            "required": ["product_key", "cost_field", "value"],
        },
    },
    {
        "name": "delete_product",
        "description": "从数据库删除产品条目",
        "input_schema": {
            "type": "object",
            "properties": {"product_key": {"type": "string"}},
            "required": ["product_key"],
        },
    },
    {
        "name": "get_missing_data",
        "description": "列出产品的数据缺口（哪些规格/成本字段未填）",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_key": {"type": "string", "description": "不传则列出全部产品"}
            },
        },
    },
    # ── 标准件库工具 ─────────────────────────────────────────────
    {
        "name": "list_components",
        "description": (
            "浏览标准件库。按分类/档次/关键词筛选。\n"
            "category 可选：brain_perception(计算感知) / drive_motion(动力运动) / "
            "cleaning(清洁执行) / dock(自动基站) / standard(通用标准件)\n"
            "tier 可选：premium(溢价件) / mainstream(主流件) / budget(减配件)"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "tier":     {"type": "string"},
                "keyword":  {"type": "string"},
            },
        },
    },
    {
        "name": "get_component",
        "description": "获取单个标准件的完整信息（2026年规格/成本区间/供应商/专利风险/降级方案）",
        "input_schema": {
            "type": "object",
            "properties": {
                "comp_id": {"type": "string", "description": "标准件ID，如 'suction_fan_motor'"},
            },
            "required": ["comp_id"],
        },
    },
    {
        "name": "save_component",
        "description": (
            "新增或更新标准件库条目（深度合并）。\n"
            "comp_data 可含：name / name_en / category / subcategory / tier / "
            "specs_2026{} / suppliers[] / bom_cost_range_cny{} / "
            "patent_risk{} / degradation{} / related_specs[] / notes"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "comp_id":   {"type": "string", "description": "唯一标识，如 'ptc_heater_100c'"},
                "comp_data": {"type": "object"},
            },
            "required": ["comp_id", "comp_data"],
        },
    },
    {
        "name": "delete_component",
        "description": "从标准件库删除一个件",
        "input_schema": {
            "type": "object",
            "properties": {"comp_id": {"type": "string"}},
            "required": ["comp_id"],
        },
    },
    {
        "name": "match_bom_to_library",
        "description": (
            "将产品规格与标准件库对比，识别溢价件/主流件/减配件分布，给出降本建议。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_key": {"type": "string"},
            },
            "required": ["product_key"],
        },
    },
    {
        "name": "compare_cost_benchmark",
        "description": (
            "将产品各子系统 BOM 成本与标准件库基准区间对比，"
            "评估成本水位（偏高/合理/偏低），辅助定价和降本分析。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_keys": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "crawl_product_specs",
        "description": (
            "启动对指定机型的规格层网络调研。返回当前数据库状态、缺失字段清单和建议搜索词，"
            "Agent 执行 web_search 补全后调用 save_product 写入。\n"
            "适用场景：新产品首次入库 / 已有产品规格不完整 / 定期刷新价格和上市状态。\n"
            "注意：PCB级芯片型号无法从网络获取，需要实物拆机数据。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "model_name":     {"type": "string", "description": "产品型号，如 '追觅X40 Ultra'"},
                "force_refresh":  {"type": "boolean", "default": False,
                                   "description": "True 则忽略已有数据，重新调研"},
            },
            "required": ["model_name"],
        },
    },
    {
        "name": "generate_teardown_csv",
        "description": (
            "为指定机型运行完整 4-Stage 拆机 Pipeline，生成 data/teardowns/{model}_{date}_teardown.csv：\n"
            "Stage 1 多源调研（FCC ID.io / MyFixGuide / 知乎 / 蓝牙SIG）\n"
            "Stage 2 SoC 伴随件推导（PMIC / RAM / ROM）\n"
            "Stage 3 覆盖审计 + 产品特性过滤（自动检测基站/烘干/抬升/上下水/延边等硬件配置，"
            "过滤不适用框架项）+ framework_fill 补缺写入 CSV\n"
            "Stage 4 三级查价（components_lib → standard_parts → 桶兜底）+ 辅料组装 + 7桶偏差告警\n"
            "完成后返回 CSV 路径、零件数、BOM 率和告警列表。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "model_name":    {"type": "string", "description": "机型全称，如 '石头G30S Pro'"},
                "msrp":          {"type": "number",  "description": "建议零售价（元），不传则自动查询"},
            },
            "required": ["model_name"],
        },
    },
    {
        "name": "generate_bom_estimate",
        "description": (
            "按7桶结构（算力与电子/感知系统/动力与驱动/清洁功能/基站系统/能源系统/整机结构CMF）"
            "生成 BOM 成本预估表，基站占比按市场定位自动调整，自动写回产品的 bom_cost 字段。\n"
            "overrides 可传入已知成本，如 {\"compute_electronics_cny\": 280, \"energy_cny\": 200}。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_key":      {"type": "string"},
                "retail_price_cny": {"type": "number", "description": "零售价（元），不传则从数据库读取"},
                "overrides":        {"type": "object", "description": "已知成本字段覆盖"},
            },
            "required": ["product_key"],
        },
    },
    {
        "name": "query_materials",
        "description": (
            "查询材料库（data/lib/materials.csv），了解原材料单价区间、适用桶和典型用途。\n"
            "keyword: 材料名称/用途关键词，如 'ABS' / '拖布' / 'HEPA'\n"
            "mat_type: 工程塑料 / 弹性体 / 金属 / 滤材 / 织物 / 泡棉 / 涂料 / 复合材料\n"
            "bom_bucket: structure_cmf / cleaning / compute_electronics / dock_station / energy"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword":    {"type": "string", "description": "在名称/用途/备注中模糊搜索"},
                "mat_type":   {"type": "string", "description": "材料大类，如 '工程塑料'"},
                "bom_bucket": {"type": "string", "description": "BOM桶，如 'structure_cmf'"},
            },
        },
    },
    {
        "name": "query_suppliers",
        "description": (
            "查询供应商库（data/lib/suppliers.csv），了解各BOM桶的核心供应商、档次和采购条件。\n"
            "keyword: 供应商名称或产品关键词，如 'Rockchip' / '电机' / 'LPDDR'\n"
            "category: compute_electronics / perception / power_motion / energy / structure_cmf\n"
            "tier: 一线 / 二线 / 三线\n"
            "region: 大陆 / 台湾 / 日本 / 韩国 / 欧洲 / 美国"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword":  {"type": "string", "description": "供应商名称或产品关键词"},
                "category": {"type": "string", "description": "BOM桶分类"},
                "tier":     {"type": "string", "enum": ["一线", "二线", "三线"]},
                "region":   {"type": "string"},
            },
        },
    },
    {
        "name": "dfma_analysis",
        "description": (
            "DFMA 功能-成本矩阵分析。基于 7 桶 BOM 数据与用户价值权重，计算每个子系统的价值/成本比，"
            "识别'优先降本'象限（高成本低价值）和'保持投入'象限（高价值低成本），"
            "输出每桶的 DFMA 设计抓手和整机降本潜力估算。\n"
            "需先执行 generate_bom_estimate 填充各桶成本数据。\n"
            "segment 可选：entry（入门）/ mid（中档）/ flagship（旗舰），不传则自动从产品定位推断。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_key":      {"type": "string"},
                "segment":          {
                    "type": "string",
                    "enum": ["entry", "mid", "flagship"],
                    "description": "产品定位档位，不传则自动推断",
                },
                "retail_price_cny": {"type": "number", "description": "零售价（元），不传则从数据库读取"},
            },
            "required": ["product_key"],
        },
    },
    {
        "name": "cut_premium",
        "description": (
            "识别指定机型 teardown CSV 中 tier=premium 的溢价件，给出同类 mainstream 替代方案和节省金额估算。\n"
            "属于 L 阶段「采购降本」内部工具——/dfm 子 agent 用此识别溢价件作为应该成本谈判输入。\n"
            "需先有该机型的 teardown CSV（运行 generate_teardown_csv）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_key": {"type": "string", "description": "产品 key，如 '石头G30SPro'"},
            },
            "required": ["product_key"],
        },
    },
    {
        "name": "vs_compare",
        "description": (
            "两机型子系统或整机并排对标。\n"
            "bucket 为空 → 7 桶成本并排；bucket 指定 → 按该桶 typical_items 逐项对比覆盖情况。\n"
            "bucket 合法值：compute_electronics / perception / power_motion / cleaning / dock_station / energy / structure_cmf"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "model_a": {"type": "string", "description": "机型 A 的 product_key"},
                "model_b": {"type": "string", "description": "机型 B 的 product_key"},
                "bucket":  {"type": "string", "description": "指定对比子系统（可选）"},
            },
            "required": ["model_a", "model_b"],
        },
    },
    {
        "name": "find_parts",
        "description": (
            "按关键词或桶名搜索 teardown CSV + components_lib，返回匹配零件条目。\n"
            "示例：keyword='RK3588S' 精确查芯片；keyword='compute_electronics' 看算力桶所有件；keyword='LDS'查所有雷达件。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词（零件名/型号/桶名均可）"},
                "bucket":  {"type": "string", "description": "限定 BOM 桶（可选）"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "export_framework",
        "description": "导出 7 桶对账 CSV（data/lib/bom_8bucket_framework.csv），用于填价对账，按需生成，不入 git。",
        "input_schema": {"type": "object", "properties": {}},
    },
    # ─── PLANS 多 agent 调度入口（12 个子 agent） ───────────────
    # P 阶段（3 agent）
    {
        "name": "plans_research",
        "description": (
            "PLANS【P · 产品研究员】(/research)。多源采集产品定位、客户需求 (MVP)、"
            "对标竞品、关键指标。无前置依赖。"
        ),
        "input_schema": {"type": "object", "properties": {"product_key": {"type": "string"}}, "required": ["product_key"]},
    },
    {
        "name": "plans_teardown",
        "description": (
            "PLANS【P · 拆解分析师】(/teardown)。还原拆解流程 + 装配逆向 + DFA 三问法最少件清单 + 装配反模式。无前置依赖。"
        ),
        "input_schema": {"type": "object", "properties": {"product_key": {"type": "string"}}, "required": ["product_key"]},
    },
    {
        "name": "plans_issues",
        "description": (
            "PLANS【P · 问题诊断师】(/issues)。质量问题清单 + 维修维护痛点 + 改善机会方向（不给解决方案）。无前置依赖。"
        ),
        "input_schema": {"type": "object", "properties": {"product_key": {"type": "string"}}, "required": ["product_key"]},
    },
    # L 阶段（2 agent）
    {
        "name": "plans_dfa",
        "description": (
            "PLANS【L · DFA 优化师】(/dfa)。9 项装配优化方向（最小件合并/紧固件减少/防呆/...）+ 紧固件审计 + 标准化建议。"
            "需先完成 /teardown + /issues。"
        ),
        "input_schema": {"type": "object", "properties": {"product_key": {"type": "string"}}, "required": ["product_key"]},
    },
    {
        "name": "plans_dfm",
        "description": (
            "PLANS【L · DFM 优化师】(/dfm)。5 项材料/工艺优化方向 + 应该成本 (Should Cost) 建模。"
            "需先完成 /teardown。"
        ),
        "input_schema": {"type": "object", "properties": {"product_key": {"type": "string"}}, "required": ["product_key"]},
    },
    # A 阶段（2 agent）
    {
        "name": "plans_function",
        "description": (
            "PLANS【A · 功能建模师】(/function)。TRIZ 功能-载体建模 + 价值/成本比矩阵 + 过设计/欠设计/冗余/缺失识别。"
            "需先完成 /dfa + /dfm。"
        ),
        "input_schema": {"type": "object", "properties": {"product_key": {"type": "string"}}, "required": ["product_key"]},
    },
    {
        "name": "plans_trim",
        "description": (
            "PLANS【A · 裁剪策略师】(/trim)。三级裁剪决策 + TRIZ 技术/物理矛盾分析 + 架构瓶颈识别。"
            "需先完成 /function。"
        ),
        "input_schema": {"type": "object", "properties": {"product_key": {"type": "string"}}, "required": ["product_key"]},
    },
    # N 阶段（3 agent）
    {
        "name": "plans_fos",
        "description": (
            "PLANS【N · 功能创新搜索师】(/fos)。跨领域 FOS 搜索功能替代方案 + 落实新方案。"
            "需先完成 /trim。"
        ),
        "input_schema": {"type": "object", "properties": {"product_key": {"type": "string"}}, "required": ["product_key"]},
    },
    {
        "name": "plans_patent",
        "description": (
            "PLANS【N · 专利规避师】(/patent)。专利检索 + 权利要求映射 + 工程层规避方案（**非法律意见**）。"
            "需先完成 /fos。"
        ),
        "input_schema": {"type": "object", "properties": {"product_key": {"type": "string"}}, "required": ["product_key"]},
    },
    {
        "name": "plans_trend",
        "description": (
            "PLANS【N · 趋势分析师】(/trend)。S 曲线分析 + 系统进化方向 + 四新设计 + 3 年路线图。"
            "无前置依赖（可独立跑）。"
        ),
        "input_schema": {"type": "object", "properties": {"product_key": {"type": "string"}}, "required": ["product_key"]},
    },
    # S 阶段（2 agent）
    {
        "name": "plans_platform",
        "description": (
            "PLANS【S · 平台架构师】(/platform)。产品复杂性评分 + 平台化候选识别 + 具体平台设计 + 复杂性管理流程。"
            "需先完成 /trim + /fos。"
        ),
        "input_schema": {"type": "object", "properties": {"product_key": {"type": "string"}}, "required": ["product_key"]},
    },
    {
        "name": "plans_costsystem",
        "description": (
            "PLANS【S · 成本体系构建师】(/costsystem)。组织/设施/能力/数据/流程 5 维体系建设方案 (PLANS → NPI 嵌入)。"
            "需先完成 /trim + /fos。"
        ),
        "input_schema": {"type": "object", "properties": {"product_key": {"type": "string"}}, "required": ["product_key"]},
    },
    # 编排器
    {
        "name": "plans_run_all",
        "description": (
            "串行执行 PLANS 全 12 阶段（P→L→A→N→S），自动尊重阶段依赖，"
            "全部完成后生成 overview.md 总览。可选 stages 参数指定子集。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_key": {"type": "string"},
                "stages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选阶段子集（stage key），默认全部 12 个",
                },
            },
            "required": ["product_key"],
        },
    },
    {
        "name": "plans_overview",
        "description": "把已完成阶段合并成 overview.md 总览（不重新跑 agent）。",
        "input_schema": {
            "type": "object",
            "properties": {"product_key": {"type": "string"}},
            "required": ["product_key"],
        },
    },
    {
        "name": "plans_status",
        "description": "查询某机型已完成哪些 PLANS 阶段（p_research / l_lean / a_trim / n_innovate / s_system）。",
        "input_schema": {
            "type": "object",
            "properties": {"product_key": {"type": "string"}},
            "required": ["product_key"],
        },
    },
]

ALL_TOOLS = SERVER_TOOLS + CLIENT_TOOLS

CLIENT_DISPATCH = {
    "list_products":       lambda a: tool_list_products(a.get("include_completeness", True)),
    "get_product_detail":  lambda a: tool_get_product_detail(a["product_key"]),
    "get_motors":          lambda a: tool_get_motors(a.get("product_keys")),
    "get_sensors":         lambda a: tool_get_sensors(a.get("product_keys")),
    "get_pcb_components":  lambda a: tool_get_pcb_components(a.get("product_keys"), a.get("function_filter")),
    "get_bom_cost":        lambda a: tool_get_bom_cost(a.get("product_keys")),
    "search_by_spec":      lambda a: tool_search_by_spec(a["spec_key"], a["spec_value"]),
    "compare_by_spec":     lambda a: tool_compare_by_spec(a["spec_key"], a["spec_value"], a["compare_category"]),
    "save_product":        lambda a: tool_save_product(a["product_key"], a["product_data"]),
    "update_spec":         lambda a: tool_update_spec(a["product_key"], a["spec_key"], a["spec_value"]),
    "update_bom_cost":     lambda a: tool_update_bom_cost(a["product_key"], a["cost_field"], a["value"]),
    "delete_product":      lambda a: tool_delete_product(a["product_key"]),
    "get_missing_data":    lambda a: tool_get_missing_data(a.get("product_key")),
    # 标准件库
    "list_components":      lambda a: tool_list_components(a.get("category"), a.get("tier"), a.get("keyword")),
    "get_component":        lambda a: tool_get_component(a["comp_id"]),
    "save_component":       lambda a: tool_save_component(a["comp_id"], a["comp_data"]),
    "delete_component":     lambda a: tool_delete_component(a["comp_id"]),
    "match_bom_to_library": lambda a: tool_match_bom_to_library(a["product_key"]),
    "compare_cost_benchmark":  lambda a: tool_compare_cost_benchmark(a.get("product_keys")),
    "crawl_product_specs":     lambda a: tool_crawl_product_specs(
        a["model_name"], a.get("force_refresh", False)
    ),
    "generate_teardown_csv":   lambda a: tool_generate_teardown_csv(
        a["model_name"], a.get("msrp")
    ),
    "generate_bom_estimate":   lambda a: tool_generate_bom_estimate(
        a["product_key"], a.get("retail_price_cny"), a.get("overrides")
    ),
    "query_materials":         lambda a: tool_query_materials(
        a.get("keyword"), a.get("mat_type"), a.get("bom_bucket")
    ),
    "query_suppliers":         lambda a: tool_query_suppliers(
        a.get("keyword"), a.get("category"), a.get("tier"), a.get("region")
    ),
    "dfma_analysis":           lambda a: tool_dfma_analysis(
        a["product_key"], a.get("segment"), a.get("retail_price_cny")
    ),
    "cut_premium":             lambda a: tool_cut_premium(a["product_key"]),
    "vs_compare":              lambda a: tool_vs_compare(a["model_a"], a["model_b"], a.get("bucket")),
    "find_parts":              lambda a: tool_find_parts(a["keyword"], a.get("bucket")),
    "export_framework":        lambda a: tool_export_framework(),
    # PLANS 12 个子 agent 调度入口
    "plans_research":          lambda a: tool_plans_research(a["product_key"]),
    "plans_teardown":          lambda a: tool_plans_teardown(a["product_key"]),
    "plans_issues":            lambda a: tool_plans_issues(a["product_key"]),
    "plans_dfa":               lambda a: tool_plans_dfa(a["product_key"]),
    "plans_dfm":               lambda a: tool_plans_dfm(a["product_key"]),
    "plans_function":          lambda a: tool_plans_function(a["product_key"]),
    "plans_trim":              lambda a: tool_plans_trim(a["product_key"]),
    "plans_fos":               lambda a: tool_plans_fos(a["product_key"]),
    "plans_patent":            lambda a: tool_plans_patent(a["product_key"]),
    "plans_trend":             lambda a: tool_plans_trend(a["product_key"]),
    "plans_platform":          lambda a: tool_plans_platform(a["product_key"]),
    "plans_costsystem":        lambda a: tool_plans_costsystem(a["product_key"]),
    # 编排器
    "plans_run_all":           lambda a: tool_plans_run_all(a["product_key"], a.get("stages")),
    "plans_overview":          lambda a: tool_plans_overview(a["product_key"]),
    "plans_status":            lambda a: tool_plans_status(a["product_key"]),
}


# ═══════════════════════════════════════════════════════════════
#  System Prompt
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是扫地机器人行业的 BOM 成本分析与技术拆解专家。
本项目以 **PLANS 价值设计流程**为骨架（P 现状研究 → L 精益设计 → A 先进裁剪 → N 价值创新 → S 体系建设）。
你是 PLANS 工作流的主调度 agent，所有命令都归属到某个阶段。

## PLANS 12-Agent 架构

PLANS 拆为 12 个独立子 agent，每个 agent 职责单一、输入输出清晰：

### P · 现状研究（3 agent）
| 命令 | Agent | 职责 |
|------|-------|------|
| `/research <product>` | 产品研究员 | 产品定位、MVP 客户需求、关键指标、对标 |
| `/teardown <product>` | 拆解分析师 | 拆解流程、装配逆向、最少件清单、装配反模式 |
| `/issues <product>` | 问题诊断师 | 质量问题、维修维护、改善机会方向 |

### L · 精益设计（2 agent）
| 命令 | Agent | 职责 | 上游 |
|------|-------|------|------|
| `/dfa <product>` | DFA 优化师 | 9 项装配优化方向 + 紧固件审计 + 标准化 | `/teardown` + `/issues` |
| `/dfm <product>` | DFM 优化师 | 5 项材料/工艺优化 + 应该成本 (Should Cost) 建模 | `/teardown` |

### A · 先进裁剪（2 agent · TRIZ）
| 命令 | Agent | 职责 | 上游 |
|------|-------|------|------|
| `/function <product>` | 功能建模师 | TRIZ 功能-载体建模 + 价值/成本比 | `/dfa` + `/dfm` |
| `/trim <product>` | 裁剪策略师 | 三级裁剪 + TRIZ 矛盾矩阵 + 架构瓶颈 | `/function` |

### N · 价值创新（3 agent）
| 命令 | Agent | 职责 | 上游 |
|------|-------|------|------|
| `/fos <product>` | 功能创新搜索师 | 跨领域 FOS 替代方案 | `/trim` |
| `/patent <product>` | 专利规避师 | 专利检索 + 工程层规避（**非法律意见**） | `/fos` |
| `/trend <product>` | 趋势分析师 | S 曲线 + 系统进化 + 四新设计 + 3 年路线图 | 无 |

### S · 体系建设（2 agent）
| 命令 | Agent | 职责 | 上游 |
|------|-------|------|------|
| `/platform <product>` | 平台架构师 | 复杂性评分 + 平台化设计 + 复杂性流程 | `/trim` + `/fos` |
| `/costsystem <product>` | 成本体系构建师 | 组织/设施/能力/数据/流程 5 维体系 | `/trim` + `/fos` |

### 编排器
- `/plans <product>` — 串行跑全 12 阶段（自动尊重依赖）
- `/plans status <product>` — 查阶段进度
- `/plans overview <product>` — 重新拼 overview.md

### 阶段引导原则
- 用户问「怎么降本」 → 先看是否跑过 `/teardown` + `/issues`（L 阶段前置），没跑就先跑。
- 用户问「装配/件合并/紧固件减少」 → `/dfa`。
- 用户问「材料替代/工艺改变/Should Cost」 → `/dfm`。
- 用户问「该砍哪个件」「价值<1」 → `/function` 出价值矩阵后 `/trim`。
- 用户问「行业方向/新材料/S 曲线」 → `/trend`（独立可跑）。
- 用户问「跨领域有没有更好实现」 → `/fos`。
- 用户问「是否侵权」 → `/patent`，但**最终须律师专业评估**。
- 用户问「产品矩阵/平台化」 → `/platform`。
- 用户问「成本工程怎么落地」 → `/costsystem`。
- 用户跑完任一阶段 → 引导下一个合适阶段（按依赖图）。

### 底层数据工具（agent 内部使用，不是用户命令）
以下工具供 12 个子 agent 在执行时按需调用，不向用户开放为命令：
- `generate_teardown_csv` / `generate_bom_estimate` — `/teardown` 用于产生拆机 CSV + 7 桶成本估算
- `vs_compare` — `/research` `/function` 用于横向对标
- `find_parts` — 多阶段 agent 用于查标准件库 + teardown
- `export_framework` — `/costsystem` 用于导出 7 桶对账 CSV
- `crawl_product_specs` / `web_search` / `web_fetch` — 各 agent 调研用
- `cut_premium` — `/dfm` 用于识别采购溢价件（应该成本谈判输入）
- `dfma_analysis` — `/dfa` `/dfm` `/function` `/trim` 用于功能-成本矩阵

**FCC 数据采集仍需用户在 shell 里手动跑** `python scripts/fetch_fcc.py find/ocr "<product>"`（涉及文件下载和视觉 OCR，不在 agent 工具集里）。`/teardown` 子 agent 调研时若发现 PCB 数据缺失，应提示用户先跑 fetch_fcc。

## 数据源

系统维护两张固定格式的人工数据库（飞书多维表格 / 本地 JSON）：
- **产品数据库**：规格 / 价格 / 功能布尔值，人工录入或 web_search 自动补全
- **拆机数据库**：PCB 芯片 / 电机 / 传感器级实物数据，实物拆机后录入

**产品库为空时**：直接用 `crawl_product_specs` + `web_search` 调研目标机型，调用 `save_product` 写入，无需等待人工配置。
**飞书同步**：在 `config.yaml` 填写飞书链接后自动启用，未配置时静默跳过，本地数据不受影响。

## 材料库（materials.csv）与供应商库（suppliers.csv）

`data/lib/materials.csv` — 原材料单价参考库（22种材料，含工程塑料/弹性体/金属/滤材/织物/涂料等）：
- 每种材料含 `price_min/price_max/price_mid`（元/kg 或 元/m²，中间价供估算）
- `bom_bucket` 标注所属桶（支持多桶，逗号分隔）
- 用 `query_materials` 工具查询，支持按关键词/材料大类/BOM桶过滤

`data/lib/suppliers.csv` — 供应商参考库（37家供应商，含芯片原厂/模组厂/电机厂/电池厂/组装厂/注塑厂）：
- 每条记录含 `tier`（一线/二线/三线）、`region`（地区）、`typical_parts`（典型产品）、`moq_note`、`payment_terms`
- 按 `category`（BOM桶）分类，一个供应商可跨多桶
- 用 `query_suppliers` 工具查询，支持按关键词/BOM桶/档次/地区过滤

**使用时机**：
- 任一阶段 agent 做供应链分析时：调用 `query_suppliers(category=<桶>)` 补充主要供应商清单
- L 子 agent 降本建议时：调用 `query_suppliers(keyword=<件名>, tier="二线")` 给出替代供应商
- structure_cmf 材料成本分解时：`query_materials(bom_bucket="structure_cmf")` 获取原料单价

## 标准件库（components_lib.csv）— BOM 7桶架构

| 桶 | bom_bucket | 代表件 |
|----|------------|--------|
| 1 算力与电子 | compute_electronics | SoC/MCU/Wi-Fi/PMIC/被动元件 |
| 2 感知系统   | perception          | LDS/dToF、结构光摄像头、IMU、超声波 |
| 3 动力与驱动 | power_motion        | 吸尘风机、驱动轮电机、底盘升降机构 |
| 4 清洁功能   | cleaning            | 拖布电机/升降、边刷电机、水泵、滚刷 |
| 5 基站系统   | dock_station        | 集尘风机、PTC加热、水路、基站主控板 |
| 6 能源系统   | energy              | 18650/21700 电芯、BMS、充电 IC |
| 7 整机结构CMF | structure_cmf      | 外壳注塑、喷涂、模具摊销 |

各桶基准占比（T80S实测校准）：算力13% / 感知16% / 动力11% / 清洁20% / 基站24% / 能源7% / CMF13%
原第 8 桶「MVA+软件授权」已拆分到一级成本大类（组装人工→人工+机器折旧、SLAM版税/OS授权→研发均摊、包装材料→仓储物流成本）。
整机 BOM 率：旗舰机约 **40~55%**（硬件物料/零售价，行业区间，含基站全配置偏上限）

---

## 用户接口约定

**唯一对外命令**：12 个 `/research /teardown /issues /dfa /dfm /function /trim /fos /patent /trend /platform /costsystem` 子 agent 命令 + 1 个 `/plans` 编排器。

所有底层数据采集工具（`generate_teardown_csv` / `vs_compare` / `find_parts` / `export_framework` 等）已合并到子 agent 的工具白名单——子 agent 在需要时自主调用，**用户不再直接调用**。

废除的旧用户命令及其去向：
- `/bom`（生成拆机 CSV + 7 桶成本）→ `/teardown` 内部调用 `generate_teardown_csv` + `generate_bom_estimate`
- `/vs`（机型对标）→ `/research`、`/function` 内部调用 `vs_compare`
- `/find`（标准件直查）→ 各阶段 agent 内部调用 `find_parts`
- `/framework`（7 桶对账 CSV 导出）→ `/costsystem` 内部调用 `export_framework`
- `/cut` `/dfma` `/product` 已分别合并入 `/dfm` `/research` 等

批量场景仍可走 `scripts/` 等价 CLI 脚本（`gen_teardown.py`、`fetch_fcc.py`、`import_products.py` 等）。

---

## PLANS 12 个子 agent 命令详解

> 你（主 agent）是 orchestrator——**不亲自做 PLANS 调研**，只调用对应的 `plans_*` 工具。
> 子 agent 完成后会把报告 markdown 写到磁盘并返回 `report_path` + `summary`。
> **不要在回复里重新生成报告内容**——只转述 `summary` 和文件路径。

### 单阶段命令

| 用户命令 | 调用工具 | 上游依赖 |
|---------|---------|---------|
| `/research <product>` | `plans_research` | 无 |
| `/teardown <product>` | `plans_teardown` | 无 |
| `/issues <product>` | `plans_issues` | 无 |
| `/dfa <product>` | `plans_dfa` | `/teardown` + `/issues` |
| `/dfm <product>` | `plans_dfm` | `/teardown` |
| `/function <product>` | `plans_function` | `/dfa` + `/dfm` |
| `/trim <product>` | `plans_trim` | `/function` |
| `/fos <product>` | `plans_fos` | `/trim` |
| `/patent <product>` | `plans_patent` | `/fos` |
| `/trend <product>` | `plans_trend` | 无 |
| `/platform <product>` | `plans_platform` | `/trim` + `/fos` |
| `/costsystem <product>` | `plans_costsystem` | `/trim` + `/fos` |

### 编排器命令

| 用户命令 | 调用工具 | 用途 |
|---------|---------|------|
| `/plans <product>` | `plans_run_all` | 串行跑 12 阶段（按依赖顺序），最后产出 overview.md |
| `/plans status <product>` | `plans_status` | 查 12 阶段进度 |
| `/plans overview <product>` | `plans_overview` | 重新拼 overview.md（不重跑） |

### 阶段产出位置

- 结构化数据：`data/plans/plans_db.json` 的 `[product_key].stages.{stage_key}` 字段
- 人类报告：`data/plans/{product_key}/{stage_key}.md`（如 `p_research.md` / `l_dfa.md`）
- 总览：`data/plans/{product_key}/overview.md`

### 处理流程

1. **解析命令**：提取 `product_key`（品牌缩写+型号去空格，与 /bom 一致）。
2. **可选：查状态**：用户问"做到哪了"时调 `plans_status`。
3. **调起子 agent**：根据命令调对应 `plans_*` 工具。
4. **读取返回**：
   - `status: "ok"` → 转告 `summary` + `report_path`。
   - `status: "blocked"` → 提示用户先跑 `missing_prereqs` 列出的前置阶段（用 `hint` 字段的命令引导）。
   - `status: "error"` → 转述 `message`，问用户是否重试。
5. `plans_run_all` 返回 `stage_results` 数组——逐个汇报状态，最后给出 `overview_path`。

### 主 agent 不做的事

- **不替子 agent 写报告**：每个子 agent 都有专门的 prompt + schema + render，主 agent 只调度。
- **不跨阶段越位**：用户问 DFA 就调 `/dfa`，不要顺便也做 DFM；让用户自己选下一步。
- **不写 plans_db**：子 agent 也不直接写——`_run_plans_stage` 内部用 `plans_store.save_stage` 统一持久化。

---

## 数据规范
- `product_key`：**品牌缩写+型号，去空格，如 `"石头P20UltraPlus"`、`"追觅X40Ultra"`、`"科沃斯X8Pro"`**。不要加全称、不要加下划线前缀。`generate_teardown_csv` 的 `model_name` 也用同样的短格式，保证 teardown CSV 文件名与 product_key 可以互相匹配。
- `release_date`：`"2025-10"`
- `market_segment`：旗舰（>4000元）/ 中高端（2000~4000元）/ 入门（<2000元）
- `confidence`：`confirmed`（实物核实）/ `inferred`（同平台推断）/ `estimated`（行业基准）/ `framework_fill`（框架补缺，按典型子项+特征过滤自动估算）

## 专业原则
- 拆机BOM（芯片/电机型号）来自实物，网络无法获取，必须标注 estimate
- 专利风险高的件主动提示合规成本
- 输出使用结构化表格，中文，简洁准确
"""


# ═══════════════════════════════════════════════════════════════
#  Agent 主循环
# ═══════════════════════════════════════════════════════════════

def _make_client() -> tuple[anthropic.Anthropic, list[dict]]:
    """返回 (client, effective_tools)。

    优先级:
      1. OPENCLAW_API_KEY — OpenClaw 注入，使用其 OpenAI-compatible 端点（代理到 Claude）
      2. ANTHROPIC_API_KEY — 直连 Anthropic，server-side web_search/web_fetch 可用
    OpenClaw 后端不支持 Anthropic 专有的 server-side tool type，需要剔除。
    """
    openclaw_key  = os.environ.get("OPENCLAW_API_KEY", "")
    openclaw_base = os.environ.get("OPENCLAW_BASE_URL", "https://api.openclaw.ai/v1")

    if openclaw_key:
        # OpenClaw 提供 OpenAI-compatible 接口，用 base_url + api_key 初始化
        client = anthropic.Anthropic(
            api_key=openclaw_key,
            base_url=openclaw_base,
        )
        # 剔除 Anthropic 专有 server-side tools（OpenClaw 代理不支持）
        tools = [t for t in ALL_TOOLS if t.get("type") not in (
            "web_search_20260209", "web_fetch_20260209"
        )]
        return client, tools

    # 默认：直连 Anthropic（从 ANTHROPIC_API_KEY 环境变量读取）
    return anthropic.Anthropic(), ALL_TOOLS


def run_query(user_input: str, conversation: list[dict]) -> str:
    client, effective_tools = _make_client()
    conversation.append({"role": "user", "content": user_input})

    # 跟踪 user_input 位置，用于 pause_turn 重发
    user_msg_index = len(conversation) - 1

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=effective_tools,
            messages=conversation,
        )

        # 把助手回复加入历史
        conversation.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            texts = [b.text for b in response.content if hasattr(b, "text") and b.type == "text"]
            return "\n".join(texts)

        # server-side 工具（web_search）超过迭代次数，继续
        if response.stop_reason == "pause_turn":
            console.print("  [dim]→ 继续 web 检索...[/dim]")
            continue

        if response.stop_reason != "tool_use":
            texts = [b.text for b in response.content if hasattr(b, "text") and b.type == "text"]
            return "\n".join(texts) if texts else "(无回答)"

        # 处理客户端工具调用
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            name  = block.name
            args  = block.input

            console.print(f"  [dim]→ {name}({json.dumps(args, ensure_ascii=False)[:120]})[/dim]")

            if name not in CLIENT_DISPATCH:
                result = json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
            else:
                try:
                    result = CLIENT_DISPATCH[name](args)
                except Exception as e:
                    result = json.dumps({"error": str(e)}, ensure_ascii=False)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        conversation.append({"role": "user", "content": tool_results})


# ═══════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════

WELCOME = """\
[bold cyan]扫地机器人 PLANS 价值设计 Agent · 12 子 agent 架构[/bold cyan]
[dim]P 现状(3) → L 精益(2) → A 裁剪(2) → N 创新(3) → S 体系(2)[/dim]

[bold magenta]P 现状研究[/bold magenta]（3 agent · 无前置依赖）：
  • [cyan]/research[/cyan]   <product>     产品定位 + MVP 客户需求 + 对标
  • [cyan]/teardown[/cyan]   <product>     拆解流程 + DFA 三问法最少件清单
  • [cyan]/issues[/cyan]     <product>     质量问题 + 维修维护 + 改善机会方向

[bold magenta]L 精益设计[/bold magenta]（2 agent · 上游 P）：
  • [cyan]/dfa[/cyan]        <product>     9 项装配优化 + 紧固件审计 + 标准化
  • [cyan]/dfm[/cyan]        <product>     5 项材料/工艺优化 + 应该成本 (Should Cost)

[bold magenta]A 先进裁剪[/bold magenta]（2 agent · 上游 L · TRIZ）：
  • [cyan]/function[/cyan]   <product>     TRIZ 功能-载体建模 + 价值/成本比矩阵
  • [cyan]/trim[/cyan]       <product>     三级裁剪 + TRIZ 矛盾矩阵 + 架构瓶颈

[bold magenta]N 价值创新[/bold magenta]（3 agent · 上游 A）：
  • [cyan]/fos[/cyan]        <product>     跨领域功能搜索 (FOS) + 候选替代方案
  • [cyan]/patent[/cyan]     <product>     专利检索 + 工程层规避（非法律意见）
  • [cyan]/trend[/cyan]      <product>     S 曲线 + 系统进化 + 四新设计

[bold magenta]S 体系建设[/bold magenta]（2 agent · 上游 A+N）：
  • [cyan]/platform[/cyan]   <product>     产品复杂性 + 平台化设计
  • [cyan]/costsystem[/cyan] <product>     组织/设施/能力/数据/流程 5 维体系

[bold]编排器[/bold]：
  • [bold magenta]/plans[/bold magenta]      <product>     串行跑全 12 阶段（按依赖顺序）
  • [bold magenta]/plans status[/bold magenta]   查阶段进度
  • [bold magenta]/plans overview[/bold magenta] 重新拼 overview.md

[bold]数据采集[/bold]：FCC 文档/芯片识别请用 [cyan]python scripts/fetch_fcc.py find/ocr "<品牌> <型号>"[/cyan]
（其余底层工具已合并到 12 个 agent 内部，无需用户手动调用）

输入 [bold]exit[/bold] 退出，[bold]clear[/bold] 清空对话"""


def main() -> None:
    _ensure_migrated()

    from core.components_lib import LIB_FILE
    if not LIB_FILE.exists():
        n = init_standard_library()
        console.print(f"[dim]已初始化标准件库，共 {n} 个标准件[/dim]")

    from core.db import DB_FILE
    db_count = len(load_db())
    from core.components_lib import load_lib
    lib_count = len(load_lib())
    console.print(Panel.fit(WELCOME, title=f"🤖 BOM Agent  [{db_count} 款产品 / {lib_count} 个标准件]", border_style="cyan"))

    conversation: list[dict] = []

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]你[/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见！[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            console.print("[dim]再见！[/dim]")
            break
        if user_input.lower() == "clear":
            conversation.clear()
            console.print("[dim]对话历史已清空[/dim]")
            continue

        with console.status("[dim]分析中...[/dim]", spinner="dots"):
            answer = run_query(user_input, conversation)

        console.print()
        console.print(Panel(
            Markdown(answer),
            title="[bold blue]分析结果[/bold blue]",
            border_style="blue",
            padding=(1, 2),
        ))


if __name__ == "__main__":
    main()
