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

from core.bom_loader import get_bom_data
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

OLD_SPECS = Path(__file__).parent / "data" / "product_specs.json"

# ─── 启动时迁移旧数据（幂等） ──────────────────────────────────
def _ensure_migrated() -> None:
    from core.db import DB_FILE
    if not DB_FILE.exists() and OLD_SPECS.exists():
        n = migrate_from_old_specs(OLD_SPECS)
        if n:
            console.print(f"[dim]已从 product_specs.json 迁移 {n} 条产品数据[/dim]")

    # 同步 Excel BOM 数据到 db
    bom = get_bom_data()
    db  = load_db()
    for model_key, data in bom.items():
        if model_key not in db:
            continue
        entry = db[model_key]
        if not entry.get("motors"):
            entry["motors"] = data["motors"]
        if not entry.get("sensors"):
            entry["sensors"] = data["sensors"]
        if not entry.get("pcb_components"):
            entry["pcb_components"] = data["pcb"]
        # 同步 battery
        if data.get("others") and not entry["bom_cost"].get("battery_cost_cny"):
            battery = next((x for x in data["others"] if x.get("name") == "电池包"), None)
            if battery:
                entry["bom_cost"]["battery_cost_cny"] = battery.get("price")
        from db import save_db
        save_db(db)
        update_completeness(model_key)


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
    from db import save_db
    save_db(db)
    update_completeness(product_key)
    return json.dumps({"status": "ok", "key": product_key, "spec_key": spec_key, "value": spec_value}, ensure_ascii=False)


def tool_update_bom_cost(product_key: str, cost_field: str, value: Any) -> str:
    """更新单个BOM成本字段，cost_field 为 bom_cost 下的字段名"""
    db = load_db()
    if product_key not in db:
        return json.dumps({"error": f"产品 '{product_key}' 不存在"}, ensure_ascii=False)
    db[product_key].setdefault("bom_cost", {})[cost_field] = value
    from db import save_db
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
    from components_lib import load_lib
    db = load_db()
    if product_key not in db:
        return json.dumps({"error": f"产品 '{product_key}' 不存在"}, ensure_ascii=False)

    entry = db[product_key]
    lib = load_lib()

    # 按 related_specs 建立 spec→component 映射
    spec_to_comp: dict[str, list[dict]] = {}
    for cid, comp in lib.items():
        for spec in comp.get("related_specs", []):
            spec_to_comp.setdefault(spec, []).append({
                "id": cid,
                "name": comp.get("name"),
                "tier": TIER_NAMES.get(comp.get("tier", ""), comp.get("tier", "")),
                "bom_cost_range": comp.get("bom_cost_range_cny", {}),
                "patent_risk": comp.get("patent_risk", {}).get("level", "-"),
                "downgrade_to": comp.get("degradation", {}).get("downgrade_to"),
                "downgrade_saving_pct": comp.get("degradation", {}).get("downgrade_cost_saving_pct"),
            })

    specs = entry.get("specs", {})
    matches = []
    for spec_key, spec_val in specs.items():
        if spec_val is None:
            continue
        if spec_key in spec_to_comp:
            for comp_info in spec_to_comp[spec_key]:
                matches.append({
                    "product_spec": f"{spec_key}={spec_val}",
                    **comp_info,
                })

    # 统计溢价件数量
    premium_count = sum(1 for m in matches if "溢价" in m.get("tier", ""))
    budget_count   = sum(1 for m in matches if "减配" in m.get("tier", ""))

    return json.dumps({
        "product": product_key,
        "matched_components": matches,
        "premium_count": premium_count,
        "budget_count": budget_count,
        "notes": "match 基于 related_specs 字段关联，覆盖主要功能件。详细型号需结合 get_product_detail 分析。",
    }, ensure_ascii=False, indent=2)


def tool_compare_cost_benchmark(product_keys: list[str] | None = None) -> str:
    """
    将产品的 BOM 成本与标准件库的基准区间对比，
    评估各子系统成本是否处于"合理区间"、"偏高"或"偏低"。
    """
    from components_lib import load_lib
    db = load_db()
    targets = product_keys if product_keys else list(db.keys())
    lib = load_lib()

    # 从标准件库聚合各分类成本基准
    category_benchmarks: dict[str, dict] = {}
    for cid, comp in lib.items():
        cat = comp.get("category", "")
        cost = comp.get("bom_cost_range_cny", {})
        if cost.get("min") and cost.get("max"):
            b = category_benchmarks.setdefault(cat, {"min_sum": 0.0, "max_sum": 0.0, "components": []})
            b["min_sum"] += cost["min"]
            b["max_sum"] += cost["max"]
            b["components"].append(comp.get("name", cid))

    result = []
    for key in targets:
        if key not in db:
            continue
        entry = db[key]
        bom = entry.get("bom_cost", {})
        item = {
            "product": key,
            "retail_price_cny": entry.get("retail_price_cny"),
            "bom_fields": {},
            "benchmark_vs_actual": {},
        }

        # 对比已知 BOM 字段
        field_map = {
            "pcb_bom_cny":      "brain_perception",
            "motors_cost_cny":  "drive_motion",
            "sensors_cost_cny": "brain_perception",
            "battery_cost_cny": "standard",
        }
        for field, cat in field_map.items():
            actual = bom.get(field)
            if actual is None:
                continue
            bench = category_benchmarks.get(cat, {})
            if bench:
                if actual < bench["min_sum"] * 0.7:
                    status = "偏低（可能缺数据或减配）"
                elif actual > bench["max_sum"] * 1.3:
                    status = "偏高（溢价件或高端配置）"
                else:
                    status = "合理区间"
            else:
                status = "无基准数据"
            item["bom_fields"][field] = actual
            item["benchmark_vs_actual"][field] = {
                "actual": actual,
                "benchmark_range": f"¥{bench.get('min_sum', 0):.0f}~{bench.get('max_sum', 0):.0f}",
                "status": status,
            }
        result.append(item)

    return json.dumps({
        "category_benchmarks": {
            k: {"cost_range": f"¥{v['min_sum']:.0f}~{v['max_sum']:.0f}", "components": v["components"]}
            for k, v in category_benchmarks.items()
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

    # 建议搜索词（分层）
    search_queries = [
        f"{model_name} 规格参数 吸力 续航 越障高度 电池容量",
        f"{model_name} 导航方式 雷达 传感器 避障",
        f"{model_name} 拖布系统 基站功能 上下水",
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
            "请依次执行 suggested_queries 的搜索，提取规格后调用 save_product 写入数据库。"
            "bom_source 标注为 'web'。"
            "若 fcc_hint 非空，额外执行 fccid.io 检索：用 web_fetch 抓取 Internal Photos 和 Block Diagram，"
            "从中识别 PCB 芯片型号并写入 pcb_components，bom_source 标注 'fcc'。"
            "fcc_hint 为空（品牌未收录）时跳过此步。"
        ),
    }, ensure_ascii=False, indent=2)


def tool_generate_bom_estimate(
    product_key: str,
    retail_price_cny: float | None = None,
    overrides: dict | None = None,
) -> str:
    """
    按8桶结构生成 BOM 成本预估表，并写回 bom_cost 字段。
    overrides 可传入已知成本，格式同 bom_cost 字段名。
    如 {"compute_electronics_cny": 280, "energy_cny": 200}
    """
    db = load_db()
    if product_key not in db:
        return json.dumps({"error": f"产品 '{product_key}' 不存在"}, ensure_ascii=False)

    entry = db[product_key]
    price = retail_price_cny or entry.get("retail_price_cny") or 4599

    # 按市场定位调整 BOM 率和基站占比
    segment = (entry.get("market_segment") or "").lower()
    if "旗舰" in segment or price >= 4000:
        bom_rate, dock_ratio = 0.52, 0.22
    elif "入门" in segment or price < 2000:
        bom_rate, dock_ratio = 0.48, 0.07
    else:
        bom_rate, dock_ratio = 0.50, 0.15

    total_est = round(price * bom_rate)

    # 8桶行业基准占比（各桶之和 = 1.0）
    BUCKETS = [
        ("compute_electronics_cny", "算力与电子",   0.11, "SoC主板·MCU·Wi-Fi·被动元件"),
        ("perception_cny",          "感知系统",     0.11, "LDS/dToF·结构光摄像头·IMU·超声波"),
        ("power_motion_cny",        "动力与驱动",   0.10, "吸尘风机·驱动轮电机·底盘升降"),
        ("cleaning_cny",            "清洁功能",     0.14, "拖布驱动·水泵·水箱·边刷·滚刷"),
        ("dock_station_cny",        "基站系统",  dock_ratio, "集尘·水路·加热·基站电控·基站结构"),
        ("energy_cny",              "能源系统",     0.08, "电芯·BMS·充电IC"),
        ("structure_cmf_cny",       "整机结构CMF",  0.11, "外壳注塑·喷涂·模具摊销"),
        ("mva_software_cny",        "MVA+软件授权", None, "组装人工·算法版税·OS·包材"),
    ]

    # 最后一桶兜底：补足 100%
    fixed_sum = sum(r for _, _, r, _ in BUCKETS if r is not None)
    BUCKETS[-1] = (BUCKETS[-1][0], BUCKETS[-1][1], round(1.0 - fixed_sum, 4), BUCKETS[-1][3])

    rows = []
    total_min = 0
    total_max = 0
    bom_patch = {}

    for field, label, ratio, components in BUCKETS:
        known = ov.get(field) or entry.get("bom_cost", {}).get(field)
        if known:
            mid = known
            lo = round(known * 0.9)
            hi = round(known * 1.1)
        else:
            mid = round(total_est * ratio)
            lo  = round(total_est * ratio * 0.85)
            hi  = round(total_est * ratio * 1.15)

        total_min += lo
        total_max += hi
        rows.append({
            "子系统": label,
            "主要构成": components,
            "成本区间_cny": f"¥{lo}~{hi}",
            "中点估值_cny": mid,
            "占比_pct": f"{ratio*100:.0f}%",
            "数据来源": "已知" if (ov.get(field) or entry.get("bom_cost", {}).get(field)) else "estimate",
        })
        bom_patch[field] = mid

    bom_patch["total_bom_cny"] = round((total_min + total_max) / 2)
    bom_patch["bom_source"]    = "estimate"
    bom_patch["gross_margin_est_pct"] = round((1 - bom_patch["total_bom_cny"] / price) * 100, 1)

    # 写回 db
    from db import save_db
    entry.setdefault("bom_cost", {}).update(bom_patch)
    save_db(db)
    update_completeness(product_key)

    return json.dumps({
        "product": product_key,
        "retail_price_cny": price,
        "bom_table": rows,
        "total_bom_range_cny": f"¥{total_min}~{total_max}",
        "total_bom_midpoint_cny": bom_patch["total_bom_cny"],
        "gross_margin_est_pct": bom_patch["gross_margin_est_pct"],
        "bom_rate_pct": round(bom_patch["total_bom_cny"] / price * 100, 1),
        "note": "基于行业基准占比估算，拆机实测数据精度更高。",
    }, ensure_ascii=False, indent=2)


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
        "name": "generate_bom_estimate",
        "description": (
            "按8桶结构（算力与电子/感知系统/动力与驱动/清洁功能/基站系统/能源系统/整机结构CMF/MVA+软件授权）"
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
    "generate_bom_estimate":   lambda a: tool_generate_bom_estimate(
        a["product_key"], a.get("retail_price_cny"), a.get("overrides")
    ),
}


# ═══════════════════════════════════════════════════════════════
#  System Prompt
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是扫地机器人行业的 BOM 成本分析与技术拆解专家。

## 数据源

系统维护两张固定格式的人工数据库（飞书多维表格 / 本地 JSON）：
- **产品数据库**：规格 / 价格 / 功能布尔值，人工录入或 web_search 自动补全
- **拆机数据库**：PCB 芯片 / 电机 / 传感器级实物数据，实物拆机后录入

**产品库为空时**：直接用 `crawl_product_specs` + `web_search` 调研目标机型，调用 `save_product` 写入，无需等待人工配置。
**飞书同步**：在 `config.yaml` 填写飞书链接后自动启用，未配置时静默跳过，本地数据不受影响。

## 标准件库（components_lib.csv）— BOM 8桶架构

| 桶 | bom_bucket | 代表件 |
|----|------------|--------|
| 1 算力与电子 | compute_electronics | SoC/MCU/Wi-Fi/PMIC/被动元件 |
| 2 感知系统   | perception          | LDS/dToF、结构光摄像头、IMU、超声波 |
| 3 动力与驱动 | power_motion        | 吸尘风机、驱动轮电机、底盘升降机构 |
| 4 清洁功能   | cleaning            | 拖布电机/升降、边刷电机、水泵、滚刷 |
| 5 基站系统   | dock_station        | 集尘风机、PTC加热、水路、基站主控板 |
| 6 能源系统   | energy              | 18650/21700 电芯、BMS、充电 IC |
| 7 整机结构CMF | structure_cmf      | 外壳注塑、喷涂、模具摊销 |
| 8 MVA+软件授权 | mva_software      | 组装人工、OS授权、算法版税、包材 |

各桶基准占比：算力10~12% / 感知10~12% / 动力9~11% / 清洁12~15% / 基站20~25% / 能源7~9% / CMF10~12% / MVA8~12%
整机 BOM 率：旗舰机约 **48~55%**（零售价）

---

## BOM 成本分析标准流程（7步）

当用户发送 **"[品牌][型号]，分析 BOM 成本"** 时，**必须依序完成以下7步**：

### Step 1 — 查库
调用 `get_product_detail` 检查产品数据库是否已有该机型。
调用 `get_missing_data` 确认规格缺口和拆机数据状态。
若 motors / pcb / sensors 非空，后续 BOM 估算优先使用拆机实测值，对应桶标注 `teardown`。

### Step 2 — 网络检索
调用 `crawl_product_specs` 获取缺失字段清单、建议搜索词和 `fcc_hint`。
执行 `web_search` 补全规格层（吸力 / 续航 / 越障 / 功能布尔值 / 价格 / 上市时间）。
若 `fcc_hint` 非空，额外执行 fccid.io 检索：
- 用 `web_fetch` 抓取品牌设备列表页，找到最相近型号
- 进入该型号详情，抓取 Internal Photos 和 Block Diagram 页面
- 从照片识别 PCB 芯片型号（SoC/MCU/Wi-Fi/PMIC 等），写入 `pcb_components`，`bom_source` 标注 `fcc`
- `fcc_hint` 为空（品牌未收录）时跳过此步，PCB 桶标注 `estimate`

### Step 3 — 写入数据库
调用 `save_product` 持久化，标注：
- `bom_source: "database"` — 产品数据库（人工维护，置信度最高）
- `bom_source: "teardown"` — 拆机数据库来源
- `bom_source: "web"` — 网络调研来源
- `bom_source: "fcc"` — fccid.io 照片识别
- `bom_source: "estimate"` — 行业基准推算

### Step 4 — 技术亮点
列出 3~5 个该产品的核心技术差异点（与行业/竞品相比的创新或领先项）。

### Step 5 — BOM 估算（8桶）
调用 `generate_bom_estimate`，输出 8桶结构成本预估表（有拆机数据的桶标注 teardown，其余 estimate）。
基站占比随档位自动调整：旗舰（≥¥4000）22%、中档（¥2000~4000）15%、入门（<¥2000）7%。

| 桶 | 字段名 | 旗舰占比 | 数据来源 |
|----|--------|---------|--------|
| 算力与电子 | compute_electronics_cny | ~11% | estimate |
| 感知系统 | perception_cny | ~11% | estimate |
| 动力与驱动 | power_motion_cny | ~10% | estimate |
| 清洁功能 | cleaning_cny | ~14% | estimate |
| 基站系统 | dock_station_cny | ~22% | estimate |
| 能源系统 | energy_cny | ~8% | estimate |
| 整机结构CMF | structure_cmf_cny | ~11% | estimate |
| MVA+软件授权 | mva_software_cny | ~13% | estimate |

### Step 6 — 供应链 & 降本分析
针对核心件（SoC / 雷达 / 电芯 / 加热模组 / 风机），给出：
- 主供应商（国内 / 海外） + 主要替代厂商
- 可降级方案 + 预估节省金额（元/台）
- 专利风险提示（拖布升降 / 伸缩边刷等高风险件）

### Step 7 — 关键差异分析
调用 `compare_by_spec` 与数据库中同价位段产品对比，
指出该产品的 2~3 个核心差异点（技术 / 成本 / 定位）。

---

## 数据规范
- `product_key`：品牌+型号，如 `"追觅X40Ultra"`
- `release_date`：`"2025-10"`
- `market_segment`：旗舰（>4000元）/ 中高端（2000~4000元）/ 入门（<2000元）
- `confidence`：`confirmed`（实物核实）/ `inferred`（同平台推断）/ `estimated`（行业基准）

## 专业原则
- 拆机BOM（芯片/电机型号）来自实物，网络无法获取，必须标注 estimate
- 专利风险高的件主动提示合规成本
- 输出使用结构化表格，中文，简洁准确
"""


# ═══════════════════════════════════════════════════════════════
#  Agent 主循环
# ═══════════════════════════════════════════════════════════════

def run_query(user_input: str, conversation: list[dict]) -> str:
    client = anthropic.Anthropic()
    conversation.append({"role": "user", "content": user_input})

    # 跟踪 user_input 位置，用于 pause_turn 重发
    user_msg_index = len(conversation) - 1

    while True:
        response = client.messages.create(
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            messages=conversation,
            thinking={"type": "adaptive"},
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
[bold cyan]扫地机器人 BOM 成本分析 & 技术选型 Agent[/bold cyan]
[dim]产品数据库 + 硬件分层标准件库 | 6步产品写入流程 | 7桶BOM成本预估[/dim]

添加新产品（完整6步流程）：
  • [bold]帮我添加 [品牌][型号]，按标准流程完成技术拆解和BOM预估[/bold]

成本分析：
  • 生成 [产品名] 的7桶BOM成本预估
  • 对比四款产品的 BOM 率和毛利率
  • 列出基站系统的标准件及成本区间

技术选型：
  • 越障4cm 的产品用了哪些驱动轮电机？
  • 注塑外壳 ABS vs 改性塑料的成本差异？
  • 列出所有专利风险 high 的标准件及绕过建议

输入 [bold]exit[/bold] 退出，[bold]clear[/bold] 清空对话"""


def main() -> None:
    _ensure_migrated()

    from components_lib import LIB_FILE
    if not LIB_FILE.exists():
        n = init_standard_library()
        console.print(f"[dim]已初始化标准件库，共 {n} 个标准件[/dim]")

    from db import DB_FILE
    db_count = len(load_db())
    from components_lib import load_lib
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
