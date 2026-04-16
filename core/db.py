"""
扫地机器人产品数据库管理模块
统一管理：产品规格、BOM成本、电机/传感器/PCB 数据的来源与完整度
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

DB_FILE = Path(__file__).parent.parent / "data" / "products_db.json"

# ─── Schema 模板 ───────────────────────────────────────────────
PRODUCT_TEMPLATE: dict[str, Any] = {
    # ── 基本信息 ──────────────────────────────────────────
    "brand": "",
    "series": "",
    "model_name": "",
    "retail_price_cny": None,
    "release_date": None,          # "2023-09"
    "market_segment": None,        # 旗舰/中端/入门
    "product_page_url": None,

    # ── 数据来源与完整度 ────────────────────────────────
    "data_sources": {
        "teardown_excel": None,    # Excel sheet 名，有则填
        "web_research": [],        # 参考链接列表
        "last_updated": None,
        "completeness": {          # "complete" / "partial" / "missing"
            "basic_specs": "missing",
            "bom_cost": "missing",
            "motors": "missing",
            "sensors": "missing",
            "pcb": "missing",
        },
    },

    # ── 技术规格 ────────────────────────────────────────
    "specs": {
        # 越障与运动
        "obstacle_height_cm": None,
        "drive_wheel_type": None,          # 直流有刷 / 直流无刷
        "chassis_type": None,              # 差速 / 四驱
        # 清扫系统
        "suction_power_pa": None,
        "fan_type": None,                  # 直流无刷 / BLDC
        "brush_lift": None,                # bool
        "brush_lift_type": None,
        "side_brush_count": None,
        # 拖布系统
        "mop_lift": None,                  # bool
        "mop_lift_type": None,             # 电控/机械臂/步进电机
        "mop_lift_height_mm": None,
        "mop_rotation_rpm": None,
        "mop_count": None,
        "water_tank_ml": None,
        "self_cleaning": None,             # bool
        "hot_air_dry": None,               # bool
        # 导航与感知
        "lidar_type": None,                # 半固态/三角测距/DTOF
        "navigation": None,
        "front_vision": None,              # 前视摄像头/结构光
        "carpet_detection": None,          # 超声波/红外/无
        # 语音与交互
        "ai_voice": None,                  # 处理器型号或False
        "voice_brand": None,               # 百度/科大讯飞/自研
        # 自动集尘/清洗
        "auto_empty": None,
        "auto_wash": None,
        # 电池
        "battery_type": None,             # 18650/21700/软包
        "battery_config": None,           # "4串2并"
        "battery_capacity_mah": None,
        "battery_voltage_v": None,
        "battery_life_min": None,
        "charging_time_min": None,
        # 噪音与体积
        "noise_db_max": None,
        "dimensions_mm": None,
        "weight_kg": None,
    },

    # ── BOM 成本（7桶结构，参考行业基准分摊）────────────────
    "bom_cost": {
        # 7-bucket 标准分摊（单位：元，也可填区间字符串如 "400~500"）
        "perception_control_cny": None,    # 感知与控制（主板+摄像头+雷达）~18%
        "power_motion_cny": None,          # 动力系统（风机+驱动轮模组）~10%
        "cleaning_module_cny": None,       # 清洁模组（拖布/履带+泵+水箱）~15%
        "battery_bms_cny": None,           # 电池动力（电芯+BMS）~7%
        "dock_system_cny": None,           # 基站系统（加热+电解水+水路+触控）~35%
        "structure_cmf_cny": None,         # 机身结构与CMF（外壳+注塑+喷涂+滚刷）~10%
        "packaging_consumables_cny": None, # 包装与耗材（尘袋+滤网+包材）~5%
        "total_bom_cny": None,             # 合计预估
        # 元数据
        "bom_source": None,               # "teardown" / "estimate" / "web"
        "gross_margin_est_pct": None,
        "bom_notes": "",
        # 旧字段保留（拆机 Excel 数据使用）
        "pcb_bom_cny": None,
        "pcb_with_labor_cny": None,
        "motors_cost_cny": None,
        "sensors_cost_cny": None,
        "battery_cost_cny": None,
        "structure_cost_cny": None,
    },

    # ── 关键元器件（无 Excel 时为空列表）─────────────────
    "motors": [],        # {name, type, model, params, qty, manufacturer, unit_price_cny}
    "sensors": [],       # {name, type, qty, manufacturer, unit_price_cny, note}
    "pcb_components": [], # {board, function, model, qty, manufacturer, spec, unit_price_cny}

    "notes": "",
}


# ─── 读写 ──────────────────────────────────────────────────────
def load_db() -> dict[str, Any]:
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    return {}


def save_db(db: dict[str, Any]) -> None:
    DB_FILE.write_text(
        json.dumps(db, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── CRUD ──────────────────────────────────────────────────────
def upsert_product(key: str, data: dict[str, Any]) -> dict[str, Any]:
    """新建或更新产品条目，返回最终存储的条目"""
    db = load_db()
    existing = db.get(key, {})

    def _deep_merge(base: Any, patch: Any) -> Any:
        if isinstance(patch, dict) and isinstance(base, dict):
            result = dict(base)
            for k, v in patch.items():
                result[k] = _deep_merge(base.get(k), v)
            return result
        return patch if patch is not None else base

    # 从模板初始化再深度合并
    import copy
    entry = _deep_merge(copy.deepcopy(PRODUCT_TEMPLATE), existing)
    entry = _deep_merge(entry, data)

    # 自动更新 last_updated
    entry.setdefault("data_sources", {})["last_updated"] = date.today().isoformat()

    db[key] = entry
    save_db(db)
    return entry


def get_product(key: str) -> dict[str, Any] | None:
    return load_db().get(key)


def list_products(keys_only: bool = False) -> list:
    db = load_db()
    if keys_only:
        return list(db.keys())
    return [
        {
            "key": k,
            "brand": v.get("brand", ""),
            "model_name": v.get("model_name", ""),
            "retail_price_cny": v.get("retail_price_cny"),
            "release_date": v.get("release_date"),
            "market_segment": v.get("market_segment"),
            "completeness": v.get("data_sources", {}).get("completeness", {}),
        }
        for k, v in db.items()
    ]


def delete_product(key: str) -> bool:
    db = load_db()
    if key in db:
        del db[key]
        save_db(db)
        return True
    return False


def update_completeness(key: str) -> None:
    """根据字段填充情况自动更新完整度标签"""
    db = load_db()
    if key not in db:
        return
    entry = db[key]
    specs = entry.get("specs", {})
    bom  = entry.get("bom_cost", {})

    def _score(d: dict, required_keys: list[str]) -> str:
        filled = sum(1 for k in required_keys if d.get(k) is not None)
        if filled == 0:
            return "missing"
        if filled < len(required_keys):
            return "partial"
        return "complete"

    entry.setdefault("data_sources", {})["completeness"] = {
        "basic_specs": _score(specs, [
            "obstacle_height_cm", "suction_power_pa", "mop_lift",
            "lidar_type", "battery_capacity_mah",
        ]),
        "bom_cost": _score(bom, ["pcb_bom_cny", "battery_cost_cny"]),
        "motors":  "complete" if entry.get("motors") else "missing",
        "sensors": "complete" if entry.get("sensors") else "missing",
        "pcb":     "complete" if entry.get("pcb_components") else "missing",
    }
    db[key] = entry
    save_db(db)


# ─── 迁移旧数据 ────────────────────────────────────────────────
def migrate_from_old_specs(old_specs_path: Path) -> int:
    """将旧 product_specs.json 迁移到新数据库，返回迁移条目数"""
    if not old_specs_path.exists():
        return 0
    old = json.loads(old_specs_path.read_text(encoding="utf-8"))
    count = 0
    for key, v in old.items():
        new_entry = {
            "brand": v.get("brand", ""),
            "model_name": v.get("model", key),
            "retail_price_cny": v.get("retail_price_cny"),
            "release_date": str(v.get("release_year")) if v.get("release_year") else None,
            "data_sources": {
                "teardown_excel": v.get("source_file", "teardown.xlsx"),
                "web_research": [],
                "completeness": {},
            },
            "specs": v.get("features", {}),
            "bom_cost": {
                "pcb_bom_cny": v.get("bom_pcb_cost_cny"),
                "pcb_with_labor_cny": v.get("bom_pcb_cost_with_labor_cny"),
                "bom_source": "teardown",
            },
        }
        upsert_product(key, new_entry)
        update_completeness(key)
        count += 1
    return count
