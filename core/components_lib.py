"""
扫地机器人行业标准件库（Standard Components Library）
基于 2026 年主流全能旗舰架构
提供：关键件元数据 / 成本区间 / 供应商参考 / 降级逻辑 / 专利风险标注
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

LIB_FILE = Path(__file__).parent.parent / "data" / "components_lib.json"

# ─── Schema ──────────────────────────────────────────────────────
COMPONENT_TEMPLATE: dict[str, Any] = {
    "id": "",                        # 唯一标识，如 "suction_fan_motor"
    "name": "",                      # 中文名
    "name_en": "",                   # 英文名
    "category": "",                  # brain_perception / drive_motion / cleaning / dock / standard
    "subcategory": "",               # 二级分类
    "tier": "",                      # premium(溢价) / mainstream(主流) / budget(减配)
    "specs_2026": {},                # 2026年主流技术参数
    "suppliers": [],                 # [{name, country, tier, note}]
    "bom_cost_range_cny": {          # BOM成本区间（单颗/模组）
        "min": None,
        "max": None,
        "unit": "元/件",
        "note": "",
    },
    "patent_risk": {
        "level": "low",              # low / medium / high
        "holders": [],               # 主要专利持有方
        "description": "",
    },
    "degradation": {                 # 降级替代方案
        "upgrade_from": None,        # 此件是谁的升级版
        "downgrade_to": None,        # 降级可用什么替代
        "downgrade_cost_saving_pct": None,
    },
    "related_specs": [],             # 关联的 product.specs 字段
    "notes": "",
    "last_updated": None,
}

CATEGORY_NAMES = {
    # 对齐 8桶 BOM 框架
    "compute_electronics": "算力与电子（SoC/MCU/Wi-Fi/被动元件）",
    "perception":          "感知系统（LDS/dToF/摄像头/IMU/超声波）",
    "power_motion":        "动力与驱动（风机/驱动轮/升降机构）",
    "cleaning":            "清洁功能（拖布/水泵/水箱/边刷/滚刷）",
    "dock_station":        "基站系统（集尘/上下水/加热/电控）",
    "energy":              "能源系统（电芯/BMS/充电IC）",
    "structure_cmf":       "整机结构CMF（外壳/注塑/喷涂/模具）",
    "mva_software":        "MVA+软件授权（组装/版税/OS/包材）",
}

TIER_NAMES = {
    "premium":    "溢价件（高端专属）",
    "mainstream": "主流件（行业标配）",
    "budget":     "减配件（降本替代）",
}


# ─── 读写 ──────────────────────────────────────────────────────
def load_lib() -> dict[str, Any]:
    if LIB_FILE.exists():
        return json.loads(LIB_FILE.read_text(encoding="utf-8"))
    return {}


def save_lib(lib: dict[str, Any]) -> None:
    LIB_FILE.write_text(
        json.dumps(lib, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── CRUD ────────────────────────────────────────────────────────
def upsert_component(comp_id: str, data: dict[str, Any]) -> dict[str, Any]:
    import copy
    lib = load_lib()
    existing = lib.get(comp_id, {})

    def _merge(base: Any, patch: Any) -> Any:
        if isinstance(patch, dict) and isinstance(base, dict):
            r = dict(base)
            for k, v in patch.items():
                r[k] = _merge(base.get(k), v)
            return r
        return patch if patch is not None else base

    entry = _merge(copy.deepcopy(COMPONENT_TEMPLATE), existing)
    entry = _merge(entry, data)
    entry["id"] = comp_id
    entry["last_updated"] = date.today().isoformat()
    lib[comp_id] = entry
    save_lib(lib)
    return entry


def get_component(comp_id: str) -> dict[str, Any] | None:
    return load_lib().get(comp_id)


def list_components(
    category: str | None = None,
    tier: str | None = None,
    keyword: str | None = None,
) -> list[dict]:
    lib = load_lib()
    result = []
    for cid, entry in lib.items():
        if category and entry.get("category") != category:
            continue
        if tier and entry.get("tier") != tier:
            continue
        if keyword:
            kw = keyword.lower()
            if (
                kw not in (entry.get("name") or "").lower()
                and kw not in (entry.get("name_en") or "").lower()
                and kw not in (entry.get("subcategory") or "").lower()
                and kw not in (entry.get("notes") or "").lower()
            ):
                continue
        cost = entry.get("bom_cost_range_cny", {})
        result.append({
            "id": cid,
            "name": entry.get("name", ""),
            "category": CATEGORY_NAMES.get(entry.get("category", ""), entry.get("category", "")),
            "tier": TIER_NAMES.get(entry.get("tier", ""), entry.get("tier", "")),
            "bom_cost_range": f"¥{cost.get('min')}~{cost.get('max')}" if cost.get("min") else "待定",
            "patent_risk": entry.get("patent_risk", {}).get("level", "-"),
            "suppliers_count": len(entry.get("suppliers", [])),
        })
    return result


def delete_component(comp_id: str) -> bool:
    lib = load_lib()
    if comp_id in lib:
        del lib[comp_id]
        save_lib(lib)
        return True
    return False


# ─── 初始化标准件库 ───────────────────────────────────────────────
def init_standard_library(force: bool = False) -> int:
    """
    写入 2026 年主流架构的初始标准件数据。
    force=True 时覆盖已有条目；默认跳过已存在的。
    返回写入条目数。
    """
    lib = load_lib()
    count = 0

    def _add(comp_id: str, data: dict) -> None:
        nonlocal count
        if comp_id in lib and not force:
            return
        upsert_component(comp_id, data)
        count += 1

    # ══════════════════════════════════════════════════════════════
    # 1. 感知与控制 (perception_ctrl)
    # ══════════════════════════════════════════════════════════════

    _add("main_soc", {
        "name": "主控 SoC",
        "name_en": "Main SoC",
        "category": "perception_ctrl",
        "subcategory": "计算芯片",
        "tier": "mainstream",
        "specs_2026": {
            "cpu_core": "四核 ARM A53/A55",
            "npu_tops": "2~4 TOPS",
            "process_nm": "22~28nm",
            "typical_models": ["全志 MR153", "瑞芯微 RK3566", "瑞芯微 RV1126"],
            "ram_mb": "512~1024",
            "storage_mb": "128~256 eMMC",
        },
        "suppliers": [
            {"name": "全志科技 (Allwinner)", "country": "CN", "tier": "mainstream", "note": "MR153 主流旗舰方案"},
            {"name": "瑞芯微 (Rockchip)", "country": "CN", "tier": "mainstream", "note": "RK3566/RV1126 视觉处理强"},
            {"name": "高通 (Qualcomm)", "country": "US", "tier": "premium", "note": "极少用，成本过高"},
        ],
        "bom_cost_range_cny": {"min": 25, "max": 80, "unit": "元/颗", "note": "含 RAM+eMMC 模组约 60~120 元"},
        "patent_risk": {"level": "low", "holders": [], "description": "通用 SoC，无特定专利风险"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "stm32_mcu",
            "downgrade_cost_saving_pct": 60,
        },
        "related_specs": ["navigation", "ai_voice"],
        "notes": "BOM 中价值最高的单芯片之一。NPU 能力直接决定 AI 避障和语音交互水平。",
    })

    _add("navigation_lidar", {
        "name": "导航激光雷达 (LDS/LiDAR)",
        "name_en": "Navigation LiDAR",
        "category": "navigation",
        "subcategory": "导航传感器",
        "tier": "mainstream",
        "specs_2026": {
            "type_options": ["封闭式 dToF", "三角测距 LDS", "可升降嵌入式 LDS"],
            "range_m": "0.15~8",
            "scan_freq_hz": 5,
            "points_per_revolution": 360,
            "main_trend": "dToF 精度更高，适应低矮空间（可升降设计）",
        },
        "suppliers": [
            {"name": "玩客 (Wanke)", "country": "CN", "tier": "mainstream", "note": "国内主流供应商"},
            {"name": "乐动 (LDROBOT)", "country": "CN", "tier": "mainstream", "note": "LD19/LD14 系列广泛应用"},
            {"name": "瑞孚迪 (Livox/Lumentum)", "country": "CN/US", "tier": "premium", "note": "高精度 dToF"},
            {"name": "思岚科技 (SLAMTEC)", "country": "CN", "tier": "mainstream", "note": "RPLIDAR 系列"},
        ],
        "bom_cost_range_cny": {"min": 40, "max": 120, "unit": "元/套", "note": "dToF 方案偏高端约 80~150 元"},
        "patent_risk": {
            "level": "medium",
            "holders": ["iRobot", "科沃斯", "石头科技"],
            "description": "可升降 LDS 结构石头/追觅有专利布局，需注意外壳集成方式",
        },
        "degradation": {
            "upgrade_from": "ir_cliff_sensor",
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": ["lidar_type", "navigation"],
        "notes": "2026 年旗舰机标配可升降嵌入 dToF，激光头不再外露。入门机仍用旋转式三角测距。",
    })

    _add("obstacle_vision_module", {
        "name": "避障/视觉模组",
        "name_en": "Obstacle Vision Module",
        "category": "navigation",
        "subcategory": "视觉传感器",
        "tier": "premium",
        "specs_2026": {
            "technology": "3D 结构光 + AI 双目视觉",
            "resolution": "VGA~1MP",
            "detection_distance_cm": "5~150",
            "ai_classes": "宠物粪便/袜子/数据线/玩具 等 50+ 类",
            "processing": "本地 NPU 推理，无需联网",
        },
        "suppliers": [
            {"name": "奥比中光 (Orbbec)", "country": "CN", "tier": "premium", "note": "3D 结构光方案领导者"},
            {"name": "舜宇光学 (Sunny Optical)", "country": "CN", "tier": "mainstream", "note": "摄像头模组大厂"},
            {"name": "旷视科技 (Megvii)", "country": "CN", "tier": "premium", "note": "AI 算法方案"},
            {"name": "奇景光电 (Himax)", "country": "TW", "tier": "mainstream", "note": "双目模组"},
        ],
        "bom_cost_range_cny": {"min": 30, "max": 120, "unit": "元/模组", "note": "含镜头+ISP，3D 结构光方案成本偏高"},
        "patent_risk": {
            "level": "high",
            "holders": ["石头科技", "追觅", "科沃斯", "iRobot"],
            "description": "3D 结构光避障方案核心专利集中在石头/追觅，新进入者需注意",
        },
        "degradation": {
            "upgrade_from": "ir_cliff_sensor",
            "downgrade_to": "single_camera_2d",
            "downgrade_cost_saving_pct": 50,
        },
        "related_specs": ["front_vision", "navigation"],
        "notes": "减配方案：仅用单目 RGB 摄像头 + 软件算法，成本降 50% 但识别精度下降。",
    })

    _add("imu_sensor", {
        "name": "IMU 惯性导航传感器",
        "name_en": "Inertial Measurement Unit",
        "category": "perception_ctrl",
        "subcategory": "导航传感器",
        "tier": "mainstream",
        "specs_2026": {
            "axes": "6轴（3轴加速度计 + 3轴陀螺仪）",
            "interface": "I2C / SPI",
            "noise_density_mdps": "< 7 mdps/√Hz",
            "typical_models": ["Bosch BMI088", "InvenSense ICM-42688", "TDK ICM-42670"],
        },
        "suppliers": [
            {"name": "博世 (Bosch Sensortec)", "country": "DE", "tier": "mainstream", "note": "BMI088 工业级"},
            {"name": "应美盛 (InvenSense/TDK)", "country": "US/JP", "tier": "mainstream", "note": "ICM 系列消费级主流"},
        ],
        "bom_cost_range_cny": {"min": 3, "max": 12, "unit": "元/颗", "note": "消费级 3~8 元，工业级 8~15 元"},
        "patent_risk": {"level": "low", "holders": [], "description": "标准传感器，无特殊专利风险"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "single_axis_gyro",
            "downgrade_cost_saving_pct": 40,
        },
        "related_specs": ["navigation"],
        "notes": "PCB BOM 中通常归于传感器类。防漂移算法（卡尔曼滤波）是软件竞争力。",
    })

    # ══════════════════════════════════════════════════════════════
    # 2. 动力与运动系统 (drive_motion)
    # ══════════════════════════════════════════════════════════════

    _add("drive_wheel_module", {
        "name": "驱动轮模组",
        "name_en": "Drive Wheel Module",
        "category": "power_motion",
        "subcategory": "底盘驱动",
        "tier": "mainstream",
        "specs_2026": {
            "motor_type": "直流有刷 或 直流无刷（高端）",
            "gearbox": "行星减速器",
            "obstacle_height_mm": "20~30mm（旗舰 ≥20mm）",
            "wheel_diameter_mm": "70~90",
            "suspension": "弹簧高挂载悬挂",
            "qty_per_robot": 2,
        },
        "suppliers": [
            {"name": "兆威机电", "country": "CN", "tier": "mainstream", "note": "国内驱动轮电机主要供应商"},
            {"name": "友嘉 (UCT)", "country": "CN", "tier": "mainstream", "note": "定制驱动轮模组"},
            {"name": "XCMOTOR", "country": "CN", "tier": "mainstream", "note": "科沃斯供应链"},
            {"name": "德昌电机 (Johnson Electric)", "country": "HK", "tier": "premium", "note": "高端有刷方案"},
        ],
        "bom_cost_range_cny": {"min": 15, "max": 50, "unit": "元/颗", "note": "含减速箱整体模组约 30~100 元/套"},
        "patent_risk": {
            "level": "medium",
            "holders": ["科沃斯", "石头科技"],
            "description": "高挂载悬挂结构（高越障）各大厂均有专利布局",
        },
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "drive_wheel_brushed_basic",
            "downgrade_cost_saving_pct": 40,
        },
        "related_specs": ["obstacle_height_cm", "drive_wheel_type", "chassis_type"],
        "notes": "越障能力核心。有刷 vs 无刷：无刷寿命长 3~5 倍，成本高约 2 倍。",
    })

    _add("suction_fan_motor", {
        "name": "吸尘风机（涡轮电机）",
        "name_en": "Suction Fan Motor (Turbine)",
        "category": "power_motion",
        "subcategory": "清扫动力",
        "tier": "mainstream",
        "specs_2026": {
            "motor_type": "直流无刷 BLDC",
            "suction_pa_range": "10000~25000 Pa",
            "rpm_range": "60000~100000 rpm",
            "power_w_range": "25~60 W",
            "noise_db_typical": "62~72 dB(A)",
            "main_trend": "超高压 20000Pa+ 已成旗舰标配，隔振降噪设计提升体验",
        },
        "suppliers": [
            {"name": "尼得科 (Nidec)", "country": "JP", "tier": "premium", "note": "高端风机标杆"},
            {"name": "万至达 (Wantechler)", "country": "CN", "tier": "mainstream", "note": "国内主流"},
            {"name": "恒驱 (Hengsmart)", "country": "CN", "tier": "mainstream", "note": "中端主力供应商"},
            {"name": "大叶 (Davy)", "country": "CN", "tier": "budget", "note": "入门机常用"},
        ],
        "bom_cost_range_cny": {"min": 20, "max": 80, "unit": "元/颗", "note": "25000Pa 高压方案约 60~100 元"},
        "patent_risk": {"level": "low", "holders": [], "description": "风机属标准部件，无重大专利壁垒"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "suction_fan_brushed",
            "downgrade_cost_saving_pct": 50,
        },
        "related_specs": ["suction_power_pa", "fan_type", "noise_db_max"],
        "notes": "功耗与噪音的核心平衡点。越障+超高吸力旗舰机整机峰值功率可达 80W+。",
    })

    _add("chassis_lift_mechanism", {
        "name": "底盘升降机构",
        "name_en": "Chassis Lift Mechanism",
        "category": "power_motion",
        "subcategory": "底盘结构",
        "tier": "premium",
        "specs_2026": {
            "technology": "电机驱动 蜗轮蜗杆 或 连杆机构",
            "lift_height_mm": "5~15",
            "motor_type": "步进电机 或 直流减速电机",
            "purpose": "应对长毛地毯，抬起拖布模组防污染",
            "trend": "2026 旗舰标配，连杆方案成本更低",
        },
        "suppliers": [
            {"name": "德昌电机 (Johnson Electric)", "country": "HK", "tier": "mainstream", "note": "步进电机方案"},
            {"name": "兆威机电", "country": "CN", "tier": "mainstream", "note": "小型减速电机"},
        ],
        "bom_cost_range_cny": {"min": 8, "max": 25, "unit": "元/套", "note": "含电机+机构，连杆方案更经济"},
        "patent_risk": {
            "level": "high",
            "holders": ["石头科技", "追觅", "科沃斯"],
            "description": "拖布升降结构专利密集，各大厂均有布局，机械连杆方案相对安全",
        },
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "mop_fixed_no_lift",
            "downgrade_cost_saving_pct": 100,
        },
        "related_specs": ["mop_lift", "mop_lift_type", "mop_lift_height_mm"],
        "notes": "减配方案：固定拖布不升降，成本节省约 15~30 元/台，但地毯防污染能力缺失。",
    })

    # ══════════════════════════════════════════════════════════════
    # 3. 清洁执行机构 (cleaning)
    # ══════════════════════════════════════════════════════════════

    _add("main_brush_module", {
        "name": "主刷模组（0缠绕滚刷）",
        "name_en": "Main Brush Module (Anti-Tangle)",
        "category": "cleaning_system",
        "subcategory": "清扫执行件",
        "tier": "mainstream",
        "specs_2026": {
            "technology": "对旋式橡胶刷 或 带精钢刀片的切割刷",
            "anti_tangle": True,
            "brush_types": ["橡胶胶条刷", "毛胶混合刷（主流）", "V型对旋刷（高端）"],
            "motor_type": "直流无刷（与风机同轴 或 独立）",
            "trend": "2026 旗舰机均主打 0 缠绕或自动切割功能",
        },
        "suppliers": [
            {"name": "各整机厂自研 ODM", "country": "CN", "tier": "mainstream", "note": "刷头通常是定制件"},
        ],
        "bom_cost_range_cny": {"min": 5, "max": 20, "unit": "元/套", "note": "主刷本体；驱动电机另计"},
        "patent_risk": {
            "level": "medium",
            "holders": ["iRobot (V型刷)", "追觅", "科沃斯"],
            "description": "V型对旋切割结构 iRobot 有基础专利，国内厂商多有绕过方案",
        },
        "degradation": {
            "upgrade_from": "standard_bristle_brush",
            "downgrade_to": "standard_bristle_brush",
            "downgrade_cost_saving_pct": 30,
        },
        "related_specs": ["brush_lift", "brush_lift_type"],
        "notes": "刷毛材质（TPE/橡胶/硅胶）影响毛发缠绕率，是消费者核心评测指标之一。",
    })

    _add("flexi_side_brush", {
        "name": "伸缩边刷模组 (FlexiArm)",
        "name_en": "Extendable Side Brush Module",
        "category": "cleaning_system",
        "subcategory": "边角清洁",
        "tier": "premium",
        "specs_2026": {
            "technology": "机械臂结构，遇墙角自动伸出 15~25mm",
            "actuator": "步进电机 + 微型推杆",
            "detection": "TOF 或 毫米波传感器触发",
            "trend": "2026 中高端机型开始标配，提升墙角覆盖率",
        },
        "suppliers": [
            {"name": "兆威机电", "country": "CN", "tier": "mainstream", "note": "微型步进推杆"},
            {"name": "各整机厂专利自研", "country": "CN", "tier": "premium", "note": "结构为各厂自研"},
        ],
        "bom_cost_range_cny": {"min": 12, "max": 35, "unit": "元/套", "note": "含电机+机构+传感器"},
        "patent_risk": {
            "level": "high",
            "holders": ["科沃斯", "追觅", "石头科技"],
            "description": "边刷伸缩机构各大厂密集布局专利，仿制风险极高",
        },
        "degradation": {
            "upgrade_from": "fixed_side_brush",
            "downgrade_to": "fixed_side_brush",
            "downgrade_cost_saving_pct": 80,
        },
        "related_specs": ["side_brush_count"],
        "notes": "固定边刷成本约 3~8 元/套。FlexiArm 是溢价功能，主要对应旗舰机型。",
    })

    _add("mop_lift_module", {
        "name": "拖布升降模组",
        "name_en": "Mop Lift Module",
        "category": "cleaning_system",
        "subcategory": "拖地执行件",
        "tier": "mainstream",
        "specs_2026": {
            "lift_height_mm": "10~20",
            "motor_type": "步进电机 或 直流减速电机",
            "control": "电控精确升降",
            "mop_count": 2,
            "rotation_rpm": "120~200 rpm（旋转拖布旗舰方案）",
            "trend": "双旋转拖布 + 高压旋拖是 2026 旗舰标配",
        },
        "suppliers": [
            {"name": "兆威机电", "country": "CN", "tier": "mainstream", "note": "升降电机"},
            {"name": "德昌电机 (Johnson Electric)", "country": "HK", "tier": "mainstream", "note": "旋转拖布电机"},
        ],
        "bom_cost_range_cny": {"min": 15, "max": 45, "unit": "元/套", "note": "旋转+升降一体模组约 35~60 元"},
        "patent_risk": {
            "level": "high",
            "holders": ["追觅", "石头科技", "科沃斯", "云鲸"],
            "description": "旋转拖布+升降组合方案专利极其密集，是行业专利摩擦重灾区",
        },
        "degradation": {
            "upgrade_from": "flat_mop_fixed",
            "downgrade_to": "flat_mop_fixed",
            "downgrade_cost_saving_pct": 70,
        },
        "related_specs": ["mop_lift", "mop_lift_type", "mop_lift_height_mm", "mop_rotation_rpm", "mop_count"],
        "notes": "云鲸的旋转拖布方案是行业先驱，但相关专利已到期或在争议中；各厂竞相研发绕过方案。",
    })

    # ══════════════════════════════════════════════════════════════
    # 4. 自动基站系统 (dock)
    # ══════════════════════════════════════════════════════════════

    _add("ptc_heater_module", {
        "name": "PTC 加热模组（热净力/沸水洗）",
        "name_en": "PTC Heater Module",
        "category": "dock_station",
        "subcategory": "基站清洁加热",
        "tier": "premium",
        "specs_2026": {
            "heating_temp_c": "60~100 °C（旗舰支持 100°C 沸水洗）",
            "power_w": "150~500 W",
            "type": "PTC 陶瓷加热片",
            "flow_control": "需配合流量计 + 水温传感器",
            "trend": "100°C 沸水洗 2025-2026 旗舰站标配，可杀菌消毒",
        },
        "suppliers": [
            {"name": "豪迈 (Haomai)", "country": "CN", "tier": "mainstream", "note": "PTC 加热模块"},
            {"name": "TDK", "country": "JP", "tier": "premium", "note": "精密 PTC 元件"},
            {"name": "国内 PTC 小厂", "country": "CN", "tier": "budget", "note": "成本敏感型方案"},
        ],
        "bom_cost_range_cny": {"min": 15, "max": 50, "unit": "元/套", "note": "含 PTC 片+安全限温+绝缘结构"},
        "patent_risk": {
            "level": "low",
            "holders": [],
            "description": "PTC 加热本身无专利壁垒，但整体热净力系统设计各厂有专利",
        },
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "cold_water_wash",
            "downgrade_cost_saving_pct": 60,
        },
        "related_specs": ["self_cleaning", "hot_air_dry"],
        "notes": "基站占整机 BOM 的 30~40%，PTC 加热是基站中成本最高的单件之一。",
    })

    _add("dust_collector_fan", {
        "name": "基站集尘风机",
        "name_en": "Dust Collector Fan (Dock)",
        "category": "dock_station",
        "subcategory": "基站集尘",
        "tier": "mainstream",
        "specs_2026": {
            "power_w": "500~1200 W",
            "suction_type": "大功率交流感应电机 或 BLDC",
            "bag_type": "滑盖式密封集尘袋",
            "capacity_L": "2~3 L",
            "trend": "1000W+ 已成旗舰基站标配，密封袋防过敏",
        },
        "suppliers": [
            {"name": "尼得科 (Nidec)", "country": "JP", "tier": "premium", "note": "高端集尘电机"},
            {"name": "松下 (Panasonic)", "country": "JP", "tier": "mainstream", "note": "交流电机"},
            {"name": "万至达", "country": "CN", "tier": "mainstream", "note": "国内替代方案"},
        ],
        "bom_cost_range_cny": {"min": 30, "max": 80, "unit": "元/套", "note": "含电机+风道+密封袋接口"},
        "patent_risk": {"level": "low", "holders": [], "description": "集尘风机属标准家电部件"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "no_auto_empty",
            "downgrade_cost_saving_pct": 100,
        },
        "related_specs": ["auto_empty"],
        "notes": "基站有无自动集尘是中高端与入门机的核心分水岭。",
    })

    _add("flow_meter", {
        "name": "流量计",
        "name_en": "Water Flow Meter",
        "category": "dock_station",
        "subcategory": "基站水路控制",
        "tier": "mainstream",
        "specs_2026": {
            "type": "霍尔效应叶轮式",
            "flow_range_ml_min": "50~500",
            "accuracy_pct": "±3~5%",
            "purpose": "精确控制基站给水/换水量",
        },
        "suppliers": [
            {"name": "深圳各小型传感器厂", "country": "CN", "tier": "mainstream", "note": "标准化商品"},
        ],
        "bom_cost_range_cny": {"min": 2, "max": 8, "unit": "元/件", "note": "标准件，价格稳定"},
        "patent_risk": {"level": "low", "holders": [], "description": "标准传感器"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "timed_pump_control",
            "downgrade_cost_saving_pct": 80,
        },
        "related_specs": ["auto_wash", "water_tank_ml"],
        "notes": '配合浊度传感器可实现"脏水检测"，提醒换水。减配方案用定时泵代替。',
    })

    _add("turbidity_sensor", {
        "name": "浊度传感器（水质检测）",
        "name_en": "Turbidity Sensor",
        "category": "dock_station",
        "subcategory": "基站水质检测",
        "tier": "premium",
        "specs_2026": {
            "type": "光电式浊度检测",
            "output": "模拟电压 或 I2C",
            "purpose": "检测拖布清洗后废水浑浊程度，决定是否需要再次清洗",
        },
        "suppliers": [
            {"name": "国内光电传感器厂商", "country": "CN", "tier": "mainstream", "note": "定制化"},
        ],
        "bom_cost_range_cny": {"min": 3, "max": 10, "unit": "元/件", "note": ""},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "fixed_wash_cycles",
            "downgrade_cost_saving_pct": 90,
        },
        "related_specs": ["auto_wash", "self_cleaning"],
        "notes": '高端基站用于"按需清洗"，减少不必要换水频次。',
    })

    _add("solenoid_valve", {
        "name": "电磁阀（上下水控制）",
        "name_en": "Solenoid Valve",
        "category": "dock_station",
        "subcategory": "基站水路控制",
        "tier": "mainstream",
        "specs_2026": {
            "type": "常闭式二通电磁阀",
            "voltage_v": 12,
            "orifice_mm": "2~4",
            "qty_per_dock": "2~4 个（进水+排水各控制）",
        },
        "suppliers": [
            {"name": "宁波匡正科技", "country": "CN", "tier": "mainstream", "note": ""},
            {"name": "台湾 SHAKO", "country": "TW", "tier": "mainstream", "note": "品质稳定"},
        ],
        "bom_cost_range_cny": {"min": 3, "max": 12, "unit": "元/个", "note": "整站用量 2~4 个共约 15~40 元"},
        "patent_risk": {"level": "low", "holders": [], "description": "标准工业件"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "manual_water_tank",
            "downgrade_cost_saving_pct": 100,
        },
        "related_specs": ["auto_wash", "self_cleaning"],
        "notes": "基站水路系统的关键控制元件，故障率是基站可靠性的主要痛点。",
    })

    # ══════════════════════════════════════════════════════════════
    # 5. 通用标准件 (standard)
    # ══════════════════════════════════════════════════════════════

    _add("battery_cell_18650", {
        "name": "18650 锂电芯",
        "name_en": "18650 Li-ion Cell",
        "category": "battery_bms",
        "subcategory": "电芯",
        "tier": "mainstream",
        "specs_2026": {
            "capacity_mah_range": "2200~3500 mAh/节",
            "voltage_v": 3.6,
            "typical_config": "4串2并（29.6V / 4.4~7.0Ah）",
            "total_capacity_mah_typical": "4400~5200 mAh",
            "cycle_life": "500~800 次（80% 容量保持）",
            "chemistry": "NCM / NCA",
        },
        "suppliers": [
            {"name": "宁德时代 (CATL)", "country": "CN", "tier": "premium", "note": "INR18650系列"},
            {"name": "比亚迪 (BYD)", "country": "CN", "tier": "mainstream", "note": "大批量供应"},
            {"name": "亿纬锂能 (EVE)", "country": "CN", "tier": "mainstream", "note": "价格竞争力强"},
            {"name": "松下 (Panasonic)", "country": "JP", "tier": "premium", "note": "高端方案"},
        ],
        "bom_cost_range_cny": {"min": 6, "max": 15, "unit": "元/节", "note": "整包（8节）约 60~120 元"},
        "patent_risk": {"level": "low", "holders": [], "description": "标准电芯格式"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": ["battery_type", "battery_config", "battery_capacity_mah", "battery_voltage_v"],
        "notes": "主流旗舰机配置：4串2并（14.8V）或 4串2并（29.6V）。注意区分电压平台影响 BOM。",
    })

    _add("battery_cell_21700", {
        "name": "21700 锂电芯",
        "name_en": "21700 Li-ion Cell",
        "category": "battery_bms",
        "subcategory": "电芯",
        "tier": "premium",
        "specs_2026": {
            "capacity_mah_range": "4000~5000 mAh/节",
            "voltage_v": 3.6,
            "typical_config": "4串1并 或 4串2并",
            "total_capacity_mah_typical": "5200~6400 mAh",
            "cycle_life": "800~1000 次",
            "advantage": "容量更大，体积效率更高，主流于旗舰机",
        },
        "suppliers": [
            {"name": "宁德时代 (CATL)", "country": "CN", "tier": "premium", "note": ""},
            {"name": "亿纬锂能 (EVE)", "country": "CN", "tier": "mainstream", "note": ""},
            {"name": "三星 SDI", "country": "KR", "tier": "premium", "note": "30T 系列"},
        ],
        "bom_cost_range_cny": {"min": 10, "max": 22, "unit": "元/节", "note": "整包（4~8节）约 60~160 元"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": "battery_cell_18650",
            "downgrade_to": "battery_cell_18650",
            "downgrade_cost_saving_pct": 20,
        },
        "related_specs": ["battery_type", "battery_capacity_mah"],
        "notes": "追觅、石头旗舰机升级 21700 趋势明显，续航可达 300~400 分钟。",
    })

    _add("battery_cell_pouch", {
        "name": "软包锂电芯",
        "name_en": "Pouch Li-ion Cell",
        "category": "battery_bms",
        "subcategory": "电芯",
        "tier": "budget",
        "specs_2026": {
            "advantage": "形状灵活，空间利用率高",
            "disadvantage": "膨胀风险，BMS 保护要求高",
            "typical_use": "中低端机型，或特殊形状底盘",
        },
        "suppliers": [
            {"name": "国内中小电芯厂", "country": "CN", "tier": "budget", "note": ""},
        ],
        "bom_cost_range_cny": {"min": 40, "max": 80, "unit": "元/包", "note": "成本与 18650 相近，设计成本更低"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": ["battery_type"],
        "notes": "入门机和部分中端机选择，旗舰机已全面转向 18650/21700。",
    })

    _add("peristaltic_pump", {
        "name": "蠕动泵（精密给水）",
        "name_en": "Peristaltic Pump",
        "category": "cleaning_system",
        "subcategory": "水路控制",
        "tier": "mainstream",
        "specs_2026": {
            "flow_range_ml_min": "5~100",
            "control": "PWM 调速，精度高",
            "advantage": "流量精准可控，自吸能力强，无液体泄漏风险",
            "typical_use": "机身水箱精确给水，控制拖地湿度",
        },
        "suppliers": [
            {"name": "重庆贝特 (Baoding Longer)", "country": "CN", "tier": "mainstream", "note": ""},
            {"name": "国内微型泵厂商", "country": "CN", "tier": "mainstream", "note": "定制化"},
        ],
        "bom_cost_range_cny": {"min": 8, "max": 25, "unit": "元/个", "note": ""},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "gravity_water_tank",
            "downgrade_cost_saving_pct": 70,
        },
        "related_specs": ["water_tank_ml", "self_cleaning"],
        "notes": "旗舰机标配，实现分区差异化给水量（地毯边界少水、硬地多水）。",
    })

    _add("diaphragm_pump", {
        "name": "隔膜泵（大流量给水）",
        "name_en": "Diaphragm Pump",
        "category": "dock_station",
        "subcategory": "水路控制",
        "tier": "mainstream",
        "specs_2026": {
            "flow_range_ml_min": "100~600",
            "advantage": "流量大，适合基站清洗水路",
            "typical_use": "自动基站冲洗拖布，大流量冲刷需求",
        },
        "suppliers": [
            {"name": "佛山市南方泵业", "country": "CN", "tier": "mainstream", "note": ""},
            {"name": "国内微型泵厂商", "country": "CN", "tier": "mainstream", "note": ""},
        ],
        "bom_cost_range_cny": {"min": 12, "max": 30, "unit": "元/个", "note": ""},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "gravity_feed",
            "downgrade_cost_saving_pct": 70,
        },
        "related_specs": ["auto_wash", "self_cleaning"],
        "notes": "基站清洗回路常用隔膜泵，机身给水常用蠕动泵，两者配合使用。",
    })

    _add("screws_m2_m3", {
        "name": "M2/M3 不锈钢自攻螺丝",
        "name_en": "M2/M3 Stainless Self-tapping Screws",
        "category": "cmf_structure",
        "subcategory": "紧固辅料",
        "tier": "budget",
        "specs_2026": {
            "spec": "M2×4/6/8, M3×6/8/10 系列",
            "material": "不锈钢 304 或 碳钢镀镍",
            "head_type": "十字沉头 / 圆头",
            "qty_per_robot": "80~150 颗/整机",
        },
        "suppliers": [
            {"name": "国内标准件厂（宁波/温州产业链）", "country": "CN", "tier": "budget", "note": "标准商品"},
        ],
        "bom_cost_range_cny": {"min": 0.02, "max": 0.1, "unit": "元/颗", "note": "整机螺丝 BOM 约 3~8 元"},
        "patent_risk": {"level": "low", "holders": [], "description": "标准件"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": [],
        "notes": "靠近基站加热区的螺丝需选用不锈钢或耐高温材质（>100°C）。线束线径建议记录：加热回路 ≥0.75mm²，信号线 ≥0.15mm²。",
    })

    # ══════════════════════════════════════════════════════════════
    # 补充：拆机实测补录件（来自 2023 拆机 Excel）
    # ══════════════════════════════════════════════════════════════

    # ── 清洁系统补充电机 ─────────────────────────────────────────

    _add("mop_rotation_motor", {
        "name": "拖布旋转电机（BLDC）",
        "name_en": "Mop Rotation Motor (BLDC)",
        "category": "cleaning_system",
        "subcategory": "拖地动力",
        "tier": "mainstream",
        "specs_2026": {
            "motor_type": "直流无刷 BLDC",
            "qty_per_robot": 2,
            "typical_voltage_v": [12, 14.4, 20],
            "typical_models": ["BL2717O-016 (CDM MOTOR)", "PRI-3855V-2185"],
            "application": "双旋转拖布驱动，旗舰机标配",
        },
        "suppliers": [
            {"name": "CDM MOTOR", "country": "CN", "tier": "mainstream", "note": "科沃斯供应链，BL2717O-016"},
            {"name": "友贸电机", "country": "CN", "tier": "mainstream", "note": "云鲸供应链"},
        ],
        "bom_cost_range_cny": {"min": 15, "max": 35, "unit": "元/颗", "note": "2颗合计约 30~70 元"},
        "patent_risk": {"level": "medium", "holders": ["追觅", "云鲸", "科沃斯"], "description": "旋转拖布专利密集"},
        "degradation": {
            "upgrade_from": "flat_mop_dc_motor",
            "downgrade_to": "flat_mop_dc_motor",
            "downgrade_cost_saving_pct": 50,
        },
        "related_specs": ["mop_rotation_rpm", "mop_count"],
        "notes": "4款拆机产品均配备，是拖地能力的核心动力件。有刷vs无刷：无刷寿命约3~5倍，旗舰机均用无刷。",
    })

    _add("main_brush_motor", {
        "name": "滚刷电机（有刷直流）",
        "name_en": "Main Brush Motor (Brushed DC)",
        "category": "cleaning_system",
        "subcategory": "清扫动力",
        "tier": "mainstream",
        "specs_2026": {
            "motor_type": "直流有刷",
            "typical_voltage_v": 12,
            "qty_per_robot": 1,
            "typical_models": ["RS-385PH-2466 (万宝至)", "XCR390SMP2982 (XIN CHUANG)", "PRI-390SV-24100"],
            "rpm_range": "5000~15000 rpm（经减速后滚刷 300~800 rpm）",
        },
        "suppliers": [
            {"name": "万宝至 (Mabuchi)", "country": "JP/CN", "tier": "mainstream", "note": "RS-385系列，行业主流"},
            {"name": "XIN CHUANG (新创)", "country": "CN", "tier": "mainstream", "note": "科沃斯供应"},
        ],
        "bom_cost_range_cny": {"min": 5, "max": 15, "unit": "元/颗", "note": ""},
        "patent_risk": {"level": "low", "holders": [], "description": "标准有刷电机，无专利壁垒"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": ["brush_lift"],
        "notes": "万宝至 RS-385 是行业事实标准。4款拆机均使用有刷方案，BLDC滚刷为溢价选项。",
    })

    _add("brush_lift_and_arm_motor", {
        "name": "滚刷抬升 / 拖布机械臂电机",
        "name_en": "Brush Lift / Mop Arm Motor",
        "category": "cleaning_system",
        "subcategory": "升降执行",
        "tier": "mainstream",
        "specs_2026": {
            "motor_types": {
                "步进电机": "新思考 NSC24BJ48，追觅X30pro滚刷抬升",
                "直流有刷（减速）": "万宝至，石头P10pro滚刷抬升；金力JL-16P1215，拖布机械臂",
            },
            "typical_voltage_v": 12,
            "qty_per_robot": "1~2（抬升+机械臂各1）",
        },
        "suppliers": [
            {"name": "新思考 (New Motech)", "country": "TW/CN", "tier": "mainstream", "note": "步进电机方案，NSC系列"},
            {"name": "万宝至 (Mabuchi)", "country": "JP/CN", "tier": "mainstream", "note": "有刷减速电机"},
            {"name": "金力电机", "country": "CN", "tier": "mainstream", "note": "拖布机械臂专用，石头/追觅供应"},
        ],
        "bom_cost_range_cny": {"min": 5, "max": 18, "unit": "元/颗", "note": "整机用量 1~2 颗共约 10~30 元"},
        "patent_risk": {"level": "high", "holders": ["石头科技", "追觅"], "description": "滚刷抬升和拖布机械臂结构是各厂专利重点"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "no_lift",
            "downgrade_cost_saving_pct": 100,
        },
        "related_specs": ["brush_lift", "brush_lift_type", "mop_lift_type"],
        "notes": "步进电机精度更高但成本高约1.5倍；有刷减速电机成本更低，可靠性依赖限位传感器配合。",
    })

    _add("air_pump_micro", {
        "name": "气泵（微型隔膜泵）",
        "name_en": "Micro Air Pump (Diaphragm)",
        "category": "cleaning_system",
        "subcategory": "水路辅件",
        "tier": "premium",
        "specs_2026": {
            "motor_type": "直流有刷隔膜泵",
            "typical_voltage_v": [3.3, 5],
            "typical_models": ["MINI PUMP CJWP08-AB03A (厦门坤锦)", "DSB030-C (德宇鑫)"],
            "purpose": "自动清洗水路中的气压辅助或集尘气吹",
            "qty_per_robot": 1,
        },
        "suppliers": [
            {"name": "厦门坤锦电子", "country": "CN", "tier": "mainstream", "note": "追觅X30pro供应，3.3V"},
            {"name": "德宇鑫", "country": "CN", "tier": "mainstream", "note": "5V 方案"},
        ],
        "bom_cost_range_cny": {"min": 3, "max": 10, "unit": "元/颗", "note": ""},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": ["self_cleaning", "auto_wash"],
        "notes": "目前仅追觅X30pro拆机发现，用于水路气压辅助。2026年自清洁系统复杂化趋势下使用会增多。",
    })

    # ── 导航传感器补充 ───────────────────────────────────────────

    _add("structured_light_front_vision", {
        "name": "前视结构光模组（单线/双线+RGB）",
        "name_en": "Front Structured Light Vision Module",
        "category": "navigation",
        "subcategory": "前视避障",
        "tier": "mainstream",
        "specs_2026": {
            "configurations": {
                "单线结构光+RGB": "线激光¥45 + RGB模组¥15 = 约¥60（石头P10pro）",
                "双线结构光+RGB": "线激光¥60 + RGB模组¥15 = 约¥75（追觅X30pro）",
                "双线结构光+RGB+处理芯片": "结构光¥60 + 处理IC¥10~15 + RGB¥15 = 约¥85~90（科沃斯X2pro）",
            },
            "detection_distance_m": "0.05~1.5",
            "trend": "2026旗舰升级为3D结构光（奥比中光），成本升至¥120~200",
        },
        "suppliers": [
            {"name": "奥比中光 (Orbbec)", "country": "CN", "tier": "premium", "note": "3D结构光，旗舰方案"},
            {"name": "国内线激光模组厂", "country": "CN", "tier": "mainstream", "note": "线激光¥40~60，高度集成"},
            {"name": "舜宇光学", "country": "CN", "tier": "mainstream", "note": "RGB摄像头模组¥12~18"},
        ],
        "bom_cost_range_cny": {"min": 50, "max": 90, "unit": "元/套", "note": "拆机实测：¥50~90；3D方案约¥120~200"},
        "patent_risk": {"level": "high", "holders": ["石头科技", "追觅", "科沃斯"], "description": "结构光避障方案核心专利集中"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "single_ir_cliff",
            "downgrade_cost_saving_pct": 80,
        },
        "related_specs": ["front_vision"],
        "notes": "价格来自2023年拆机实测。单线→双线成本差约¥15；有无专用处理芯片差约¥10~15。",
    })

    _add("carpet_ultrasonic_sensor", {
        "name": "超声波地毯识别传感器",
        "name_en": "Ultrasonic Carpet Detection Sensor",
        "category": "navigation",
        "subcategory": "地面感知",
        "tier": "mainstream",
        "specs_2026": {
            "types": {
                "模拟输出": "汇通西电，¥12（科沃斯X2pro/石头P10pro）",
                "数字输出（高精度）": "奥迪威，¥24（追觅X30pro/云鲸J4）",
            },
            "frequency_khz": "40~200",
            "purpose": "识别地毯，自动切换吸力/抬拖布",
        },
        "suppliers": [
            {"name": "汇通西电", "country": "CN", "tier": "budget", "note": "¥12，模拟方案，4款拆机中2款使用"},
            {"name": "奥迪威 (Audiowell)", "country": "CN", "tier": "mainstream", "note": "¥24，数字输出精度更高"},
        ],
        "bom_cost_range_cny": {"min": 12, "max": 24, "unit": "元/颗", "note": "拆机实测，4款产品全部配备"},
        "patent_risk": {"level": "low", "holders": [], "description": "超声波地毯识别属标准技术"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "no_carpet_detection",
            "downgrade_cost_saving_pct": 100,
        },
        "related_specs": ["carpet_detection"],
        "notes": "4款拆机均配备，是中端以上产品标配。数字方案（奥迪威）成本2倍但灵敏度更高、误触发更少。",
    })

    _add("wall_follow_sensor", {
        "name": "沿墙传感器（TOF/PSD/线激光）",
        "name_en": "Wall Following Sensor",
        "category": "navigation",
        "subcategory": "沿墙导航",
        "tier": "mainstream",
        "specs_2026": {
            "technology_tiers": {
                "红外对管（1发2收）": "¥2，石头P10pro，基础沿墙精度",
                "PSD位置敏感探头": "¥12，追觅X30pro，中端方案",
                "TOF飞行时间": "¥12，科沃斯X2pro，精度较好",
                "线激光": "¥45，云鲸J4，高精度沿墙，也用作避障",
            },
            "range_m": "0.01~0.5",
        },
        "suppliers": [
            {"name": "国内TOF小厂", "country": "CN", "tier": "mainstream", "note": "TOF模组约¥10~15"},
            {"name": "国内线激光厂", "country": "CN", "tier": "premium", "note": "线激光约¥40~50"},
        ],
        "bom_cost_range_cny": {"min": 2, "max": 45, "unit": "元/套", "note": "拆机实测：红外¥2 / TOF/PSD¥12 / 线激光¥45"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": "ir_wall_follow",
            "downgrade_to": "ir_wall_follow",
            "downgrade_cost_saving_pct": 95,
        },
        "related_specs": ["navigation"],
        "notes": "4款拆机实测价格跨度极大（¥2~45）。线激光方案精度高但成本是TOF的3.75倍；新品趋向线激光+TOF双方案。",
    })

    # ── 感知辅件（小件，来自拆机实测）────────────────────────────

    _add("ir_sensors_bundle", {
        "name": "红外辅件组（下视/碰撞/回充/基站通讯）",
        "name_en": "IR Sensor Bundle (Cliff / Collision / Dock)",
        "category": "perception_ctrl",
        "subcategory": "机身辅助传感器",
        "tier": "mainstream",
        "specs_2026": {
            "types": "红外对管（发射+接收）",
            "unit_price_cny": 1.0,
            "typical_qty_per_robot": {
                "下视（防跌落）": "4~6 颗",
                "碰撞检测": "2~4 颗（部分用光耦替代）",
                "回充信号接收": "2~4 颗",
                "基站通讯": "1 颗",
            },
            "total_qty_typical": "10~15 颗/整机",
        },
        "suppliers": [
            {"name": "国内红外元件厂（广东/深圳）", "country": "CN", "tier": "mainstream", "note": "标准商品"},
        ],
        "bom_cost_range_cny": {"min": 8, "max": 15, "unit": "元/整机", "note": "拆机实测单价¥1/颗，整机用量10~15颗"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": [],
        "notes": "4款拆机均大量使用。下视颗数决定跌落检测覆盖范围，旗舰≥5颗。",
    })

    _add("hall_and_micro_switch_bundle", {
        "name": "霍尔 + 微动开关辅件组（编码器/安装检测）",
        "name_en": "Hall Sensor + Micro Switch Bundle",
        "category": "perception_ctrl",
        "subcategory": "机身辅助传感器",
        "tier": "mainstream",
        "specs_2026": {
            "hall_sensor": {
                "unit_price_cny": 1.5,
                "uses": "驱动轮编码器(2) / 拖布安装检测(2) / 尘盒检测(1)",
                "qty_typical": "5~8 颗/整机",
            },
            "micro_switch": {
                "unit_price_cny": 0.5,
                "uses": "驱动轮抬起检测(2) / 拖布抬起检测(1) / 对位检测(1)",
                "qty_typical": "3~6 颗/整机",
            },
        },
        "suppliers": [
            {"name": "国内霍尔IC厂（华润微等）", "country": "CN", "tier": "mainstream", "note": ""},
            {"name": "欧姆龙 (Omron)", "country": "JP", "tier": "premium", "note": "高端微动开关"},
            {"name": "国内微动开关厂", "country": "CN", "tier": "budget", "note": ""},
        ],
        "bom_cost_range_cny": {"min": 9, "max": 15, "unit": "元/整机", "note": "拆机实测：霍尔¥1~1.5/颗，微动¥0.5/颗，整机合计约¥9~15"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": [],
        "notes": "看似低价，但霍尔编码器精度直接影响导航建图质量，不建议降级。",
    })

    _add("optocoupler_position", {
        "name": "光耦位置检测件",
        "name_en": "Optocoupler Position Detector",
        "category": "perception_ctrl",
        "subcategory": "机身辅助传感器",
        "tier": "mainstream",
        "specs_2026": {
            "unit_price_cny": 0.5,
            "uses": "拖布抬起(2) / 拖布机械臂到位(2) / 滚刷抬起(1) / 碰撞(2)",
            "qty_typical": "4~8 颗/整机",
        },
        "suppliers": [
            {"name": "国内光耦厂（华晶、亿光等）", "country": "CN", "tier": "mainstream", "note": ""},
        ],
        "bom_cost_range_cny": {"min": 2, "max": 6, "unit": "元/整机", "note": "拆机实测单价¥0.5~1/颗"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": [],
        "notes": "与微动开关互为替代方案（石头P10pro用光耦做碰撞检测，科沃斯用红外对管）。",
    })

    _add("speaker_small", {
        "name": "小喇叭（语音播报）",
        "name_en": "Small Speaker",
        "category": "perception_ctrl",
        "subcategory": "人机交互",
        "tier": "mainstream",
        "specs_2026": {
            "unit_price_cny": 1.5,
            "impedance_ohm": "8",
            "diameter_mm": "20~30",
            "purpose": "语音播报（开机/报错/清洁完成）",
        },
        "suppliers": [
            {"name": "国内小喇叭厂", "country": "CN", "tier": "mainstream", "note": "4款拆机实测均为¥1.5"},
        ],
        "bom_cost_range_cny": {"min": 1.5, "max": 3, "unit": "元/颗", "note": "拆机实测¥1.5，含AI语音的旗舰机可能用更大喇叭"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": ["ai_voice", "voice_brand"],
        "notes": "4款拆机价格完全一致（¥1.5）。AI语音旗舰机通常配合功放IC，喇叭本体不变。",
    })

    # ══════════════════════════════════════════════════════════════
    # 6. 机身结构与CMF (cmf_structure) — 材质 + 加工工艺
    # ══════════════════════════════════════════════════════════════

    _add("abs_housing", {
        "name": "ABS 机身外壳",
        "name_en": "ABS Housing Shell",
        "category": "cmf_structure",
        "subcategory": "材质-外观件",
        "tier": "mainstream",
        "specs_2026": {
            "material": "ABS（改性 PC+ABS 耐冲击）",
            "density_g_cm3": 1.05,
            "typical_color": "白/黑/香槟金",
            "surface_finish": "高光/亚光/皮纹",
            "typical_weight_g": "主机外壳约 200~350g，基站外壳约 500~800g",
        },
        "suppliers": [
            {"name": "金发科技", "country": "CN", "tier": "mainstream", "note": "ABS/PC-ABS 粒料主供"},
            {"name": "LG 化学", "country": "KR", "tier": "premium", "note": "高端 PC-ABS"},
            {"name": "注塑代工厂（东莞/深圳）", "country": "CN", "tier": "mainstream", "note": "注塑加工"},
        ],
        "bom_cost_range_cny": {"min": 0.012, "max": 0.02, "unit": "元/克", "note": "外壳含料费+注塑费约 6~12 元/件（300g）"},
        "patent_risk": {"level": "low", "holders": [], "description": "材质无专利，外观设计有外观专利"},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": [],
        "notes": "主机顶盖/底盘/侧围；颜色一致性要求高。冰箱白/深空黑是主流旗舰配色。",
    })

    _add("pc_cover", {
        "name": "PC 透明传感器罩 / 导光件",
        "name_en": "PC Transparent Sensor Cover",
        "category": "cmf_structure",
        "subcategory": "材质-光学件",
        "tier": "mainstream",
        "specs_2026": {
            "material": "PC（聚碳酸酯）透明或半透",
            "transmittance_pct": ">85%",
            "typical_use": "激光雷达窗口、前视摄像头罩、状态灯导光条",
        },
        "suppliers": [
            {"name": "科思创 (Covestro)", "country": "DE", "tier": "premium", "note": "Makrolon 光学级 PC"},
            {"name": "三菱化学", "country": "JP", "tier": "mainstream", "note": ""},
        ],
        "bom_cost_range_cny": {"min": 0.025, "max": 0.05, "unit": "元/克", "note": "单件约 2~8 元"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "abs_tinted",
            "downgrade_cost_saving_pct": 30,
        },
        "related_specs": [],
        "notes": "光学级 PC 需防划伤涂层（AS 硬化）。雷达窗口平整度影响测距精度。",
    })

    _add("modified_plastic_structure", {
        "name": "改性塑料结构件（高强度）",
        "name_en": "Reinforced Plastic Structural Part",
        "category": "cmf_structure",
        "subcategory": "材质-结构件",
        "tier": "mainstream",
        "specs_2026": {
            "material_options": ["PA66-GF30（玻纤尼龙，驱动轮架）", "POM（齿轮/轴套）", "PP-TD20（底盘加强件）"],
            "typical_use": "驱动轮支架、齿轮箱壳体、升降机构支撑臂",
        },
        "suppliers": [
            {"name": "巴斯夫 (BASF)", "country": "DE", "tier": "premium", "note": "Ultramid PA66 系列"},
            {"name": "国内改性塑料厂", "country": "CN", "tier": "mainstream", "note": "PA66-GF30 大批量"},
        ],
        "bom_cost_range_cny": {"min": 0.018, "max": 0.035, "unit": "元/克", "note": "驱动轮架（约 50g）约 2~5 元/件"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "abs_housing",
            "downgrade_cost_saving_pct": 30,
        },
        "related_specs": [],
        "notes": "玻纤增强件注塑后需注意翘曲和缩痕，模具设计要求高。",
    })

    _add("injection_molding_fee", {
        "name": "注塑加工费",
        "name_en": "Injection Molding Processing Fee",
        "category": "cmf_structure",
        "subcategory": "加工工艺",
        "tier": "mainstream",
        "specs_2026": {
            "fee_structure": "吨位×工时，通常以元/模次计",
            "typical_tonnage": "80~500吨（按件大小）",
            "cycle_time_s": "15~60 秒/模",
            "fee_range_per_shot": "0.05~0.5 元/模次（含摊销）",
            "mold_cost_est": {
                "simple_cover": "3~8 万元/套",
                "complex_chassis": "15~30 万元/套",
                "dock_housing": "20~40 万元/套",
            },
        },
        "suppliers": [
            {"name": "东莞/深圳注塑代工厂", "country": "CN", "tier": "mainstream", "note": "RVC 产业链集中地"},
        ],
        "bom_cost_range_cny": {"min": 2, "max": 15, "unit": "元/件", "note": "含料费+加工费+模具摊销，大批量（>10万件/年）摊销后约 3~8 元/件"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": [],
        "notes": (
            "模具费估算公式（参考）：投影面积（cm²）× 0.8~1.2 万元/100cm²，复杂度系数 1.0~2.0。"
            "大批量时模具费摊销到单件成本 < 0.5 元。"
        ),
    })

    _add("spray_painting_fee", {
        "name": "喷涂工艺费（外观处理）",
        "name_en": "Spray Painting / Coating Fee",
        "category": "cmf_structure",
        "subcategory": "加工工艺",
        "tier": "mainstream",
        "specs_2026": {
            "process_types": {
                "UV涂装": "高光镜面效果，约 3~6 元/件",
                "橡皮漆": "柔性防滑质感，约 2~4 元/件",
                "金属漆": "珠光/金属感，约 5~10 元/件",
                "PU底漆+面漆": "耐磨高端方案，约 8~15 元/件",
            },
            "typical_passes": "底漆 1 道 + 面漆 1~2 道",
        },
        "suppliers": [
            {"name": "珠三角喷涂代工厂", "country": "CN", "tier": "mainstream", "note": ""},
            {"name": "立邦涂料 (Nippon Paint)", "country": "SG/CN", "tier": "mainstream", "note": "涂料供应"},
        ],
        "bom_cost_range_cny": {"min": 2, "max": 15, "unit": "元/件", "note": "按件计费，旗舰机多层工艺约 8~15 元/件"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "direct_molding_color",
            "downgrade_cost_saving_pct": 70,
        },
        "related_specs": [],
        "notes": "减配方案：直接随料着色（免喷涂），节省约 70% 涂装成本，但外观质感明显降档。",
    })

    _add("laser_engraving_logo", {
        "name": "镭雕 / 激光雕刻（Logo/刻字）",
        "name_en": "Laser Engraving",
        "category": "cmf_structure",
        "subcategory": "加工工艺",
        "tier": "mainstream",
        "specs_2026": {
            "typical_use": "品牌 Logo、产品型号、安规标识、按键图标",
            "process": "激光去除表面涂层或直接烧蚀塑料",
            "fee_per_piece": "0.3~1.5 元/件（按雕刻面积和复杂度）",
        },
        "suppliers": [
            {"name": "镭雕设备：大族激光 (Han's Laser)", "country": "CN", "tier": "mainstream", "note": ""},
        ],
        "bom_cost_range_cny": {"min": 0.3, "max": 1.5, "unit": "元/件", "note": ""},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "pad_printing",
            "downgrade_cost_saving_pct": 50,
        },
        "related_specs": [],
        "notes": "减配：移印（移印纸印刷），成本约 0.1~0.5 元/件，但耐久性差。",
    })

    # ══════════════════════════════════════════════════════════════
    # 7. 续航系统补充 — BMS 模块
    # ══════════════════════════════════════════════════════════════

    _add("bms_module", {
        "name": "BMS 电池管理模块",
        "name_en": "Battery Management System",
        "category": "battery_bms",
        "subcategory": "电池管理",
        "tier": "mainstream",
        "specs_2026": {
            "protection": "过充/过放/过流/短路/温度保护",
            "cell_config_support": "2S~4S 串联，1P~3P 并联",
            "communication": "UART/I2C 与主控通信（电量计/温度上报）",
            "mosfet_count": "4~8 颗保护 MOSFET",
            "typical_ic": ["德州仪器 BQ系列", "微芯 MCP73系列", "国产 JW（金微）系列"],
        },
        "suppliers": [
            {"name": "TI (Texas Instruments)", "country": "US", "tier": "premium", "note": "BQ40Z80 高精度方案"},
            {"name": "MPS / Microchip", "country": "US", "tier": "mainstream", "note": ""},
            {"name": "金微 (JW) / 南芯 (Southchip)", "country": "CN", "tier": "mainstream", "note": "国产替代方案"},
        ],
        "bom_cost_range_cny": {"min": 8, "max": 25, "unit": "元/套", "note": "含 IC+MOSFET+PCB，整套 BMS 模块"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": ["battery_type", "battery_capacity_mah", "battery_voltage_v"],
        "notes": "BMS 精度直接影响电量显示准确性和电芯寿命。旗舰机通常集成在机器人底盘 PCB 上，非独立模块。",
    })

    # ══════════════════════════════════════════════════════════════
    # 8. 包装与耗材 (packaging)
    # ══════════════════════════════════════════════════════════════

    _add("dust_bag_consumable", {
        "name": "集尘袋（耗材）",
        "name_en": "Dust Bag Consumable",
        "category": "packaging",
        "subcategory": "耗材",
        "tier": "mainstream",
        "specs_2026": {
            "capacity_L": "2~3 L",
            "filtration": "HEPA 级或抗菌材质",
            "seal_type": "滑盖自密封（防二次扬尘）",
            "replacement_cycle": "60~120 天（厂商建议）",
        },
        "suppliers": [
            {"name": "整机厂自供（耗材利润池）", "country": "CN", "tier": "mainstream", "note": "尘袋是重要后市场收入"},
        ],
        "bom_cost_range_cny": {"min": 1.5, "max": 5, "unit": "元/个", "note": "整机随箱附赠 1~2 个"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": "reusable_dust_bin",
            "downgrade_cost_saving_pct": 70,
        },
        "related_specs": ["auto_empty"],
        "notes": "耗材订阅是整机厂重要的后市场收入，尘袋零售约 ¥15~30/个，BOM 约 ¥2~5，毛利率极高。",
    })

    _add("packaging_box", {
        "name": "包装箱与辅料",
        "name_en": "Packaging Box & Accessories",
        "category": "packaging",
        "subcategory": "包装",
        "tier": "mainstream",
        "specs_2026": {
            "box_type": "E 瓦楞彩印纸箱 + EPE 珍珠棉内衬",
            "typical_weight_kg": "整机包装约 3~5 kg（含缓冲）",
            "accessories": "说明书/保修卡/清洁配件/电源线",
        },
        "suppliers": [
            {"name": "珠三角纸箱厂", "country": "CN", "tier": "mainstream", "note": ""},
        ],
        "bom_cost_range_cny": {"min": 8, "max": 20, "unit": "元/套", "note": "含纸箱+内衬+附件"},
        "patent_risk": {"level": "low", "holders": [], "description": ""},
        "degradation": {
            "upgrade_from": None,
            "downgrade_to": None,
            "downgrade_cost_saving_pct": None,
        },
        "related_specs": [],
        "notes": "旗舰机包装投入较高，礼盒感强（天地盖/磁扣）。出口版需满足 ISTA/ASTM 跌落测试。",
    })

    return count

    return count
