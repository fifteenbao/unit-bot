"""
拆机 CSV → 标准件库构建工具

读取 data/teardowns/*.csv，汇总重建 data/lib/components_lib.csv。
teardown CSV 中的 confidence 字段（estimate/web/fcc/teardown/confirmed）
原样传递到 lib，作为每条件的信息来源标注。

用法：
  python scripts/build_components.py           # 读取 data/teardowns/ 所有 CSV
  python scripts/build_components.py data/teardowns/石头G30SPro_teardown.csv  # 单文件
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR     = Path(__file__).parent.parent / "data"
TEARDOWN_DIR = DATA_DIR / "teardowns"
LIB_DIR      = DATA_DIR / "lib"
LIB_CSV      = LIB_DIR / "components_lib.csv"

TODAY = date.today().isoformat()  # e.g. "2026-04-17"

LIB_FIELDS = [
    "id", "bom_bucket", "bom_bucket_cn", "name", "name_en",
    "tier", "model_numbers", "spec", "cost_min", "cost_max", "unit",
    "suppliers", "confidence", "models", "last_updated",
]

# ── BOM 桶映射 ──────────────────────────────────────────────────

BOM_BUCKET_CN = {
    "compute_electronics": "算力与电子",
    "perception":          "感知系统",
    "power_motion":        "动力与驱动",
    "cleaning":            "清洁功能",
    "dock_station":        "基站系统",
    "energy":              "能源系统",
    "structure_cmf":       "整机结构CMF",
    "mva_software":        "MVA+软件授权",
}

# PCB 功能模块 → bom_bucket
PCB_BUCKET_MAP: dict[str, str] = {
    "CPU": "compute_electronics", "SoC": "compute_electronics",
    "NPU": "compute_electronics", "NPU/AI": "compute_electronics",
    "PMIC": "compute_electronics", "DCDC": "compute_electronics",
    "RAM": "compute_electronics", "ROM": "compute_electronics",
    "闪存": "compute_electronics",
    "WIFI": "compute_electronics", "WIFI/BT": "compute_electronics",
    "蓝牙": "compute_electronics", "蓝牙芯片": "compute_electronics",
    "马达驱动": "compute_electronics", "MCU": "compute_electronics",
    "充电IC": "compute_electronics",
    "音频": "compute_electronics", "音频放大": "compute_electronics",
    "音频解码": "compute_electronics",
    "AI语音处理": "perception", "AI语音板": "perception",
    "麦克风": "compute_electronics",
    "IMU": "perception",
    "ToF": "perception", "视觉处理": "perception",
    "多路复用开关": "compute_electronics",
    "运放": "compute_electronics",
    "阻容器件": "compute_electronics",
    "PCB": "compute_electronics",
    "LED": "compute_electronics", "按键": "compute_electronics",
    "红外发送": "perception", "红外发送灯": "perception",
    "LDO": "compute_electronics",
}

# 电机名 → bom_bucket
MOTOR_BUCKET_MAP: dict[str, str] = {
    "风机":         "power_motion",
    "驱动轮电机":   "power_motion",
    "底盘升降电机": "power_motion",
    "边刷电机":     "cleaning",
    "滚刷":         "cleaning",
    "滚刷抬升电机": "cleaning",
    "拖布电机":     "cleaning",
    "拖布震动电机": "cleaning",
    "拖布机械臂电机": "cleaning",
    "拖布抬升电机": "cleaning",
    "拖布伸缩电机": "cleaning",
    "水泵":         "cleaning",
    "气泵":         "cleaning",
}

# 传感器名 → bom_bucket
SENSOR_BUCKET_MAP: dict[str, str] = {
    "雷达":              "perception",
    "前视":              "perception",
    "ToF":               "perception",
    "沿墙":              "perception",
    "驱动轮编码器":      "power_motion",
    "碰撞":              "perception",
    "下视":              "perception",
    "地毯识别":          "perception",
    "拖布安装检测":      "cleaning",
    "滚刷抬起检测":      "cleaning",
    "底盘升降位置检测":  "power_motion",
    "尘盒安装检测":      "perception",
    "回充信号接收":      "perception",
    "基站通讯":          "dock_station",
    "对位检测":          "dock_station",
    "拖布抬起检测":      "cleaning",
    "拖布机械臂到位检测": "cleaning",
    "上盖安装检测":      "perception",
    "边刷位置检测":      "cleaning",
    "超声波驱动板":      "perception",
    "麦克风板":          "compute_electronics",
    "按键显示板":        "compute_electronics",
    "重置/USB/雷达碰撞板": "compute_electronics",
}


def _bucket_pcb(func: str, board: str) -> str:
    f = func.strip()
    if f in PCB_BUCKET_MAP:
        return PCB_BUCKET_MAP[f]
    b = board.strip()
    if "基站" in b:
        return "dock_station"
    if "导航" in b or "视觉" in b:
        return "perception"
    return "compute_electronics"


def _bucket_motor(name: str) -> str:
    for k, v in MOTOR_BUCKET_MAP.items():
        if k in name:
            return v
    return "power_motion"


def _bucket_sensor(name: str) -> str:
    for k, v in SENSOR_BUCKET_MAP.items():
        if k in name:
            return v
    return "perception"


def _bucket_other(name: str) -> str:
    if "电池" in name or "BMS" in name:
        return "energy"
    if "喇叭" in name:
        return "compute_electronics"
    return "structure_cmf"


# ── 汇总 → components_lib.csv ──────────────────────────────────

def build_lib(all_rows: list[dict]) -> list[dict]:
    registry: dict[str, dict] = {}

    for row in all_rows:
        key = f"{row['bom_bucket']}|{row['section']}|{row['name']}|{row.get('type','')}"
        model = row["product_source"]
        price = row.get("unit_price", "")

        if key not in registry:
            cost_min, cost_max = _parse_price(price)
            registry[key] = {
                "id":           _make_id(row["bom_bucket"], row["name"]),
                "bom_bucket":   row["bom_bucket"],
                "bom_bucket_cn": BOM_BUCKET_CN.get(row["bom_bucket"], row["bom_bucket"]),
                "name":         row["name"],
                "name_en":      "",
                "tier":         "mainstream",
                "model_numbers": row.get("model", ""),
                "spec":         row.get("spec", ""),
                "cost_min":     cost_min,
                "cost_max":     cost_max,
                "unit":         "元/件",
                "suppliers":    row.get("manufacturer", ""),
                "confidence":   row.get("confidence", "inferred"),
                "models":       {model},
            }
        else:
            entry = registry[key]
            entry["models"].add(model)
            # 合并供应商
            if row.get("manufacturer") and row["manufacturer"] not in entry["suppliers"]:
                entry["suppliers"] = "、".join(filter(None, [entry["suppliers"], row["manufacturer"]]))
            # 合并型号
            if row.get("model") and row["model"] not in entry.get("model_numbers", ""):
                entry["model_numbers"] = "、".join(filter(None, [entry.get("model_numbers",""), row["model"]]))
            # 优先用已确认价格
            if not entry["cost_min"] and row.get("unit_price"):
                entry["cost_min"], entry["cost_max"] = _parse_price(row["unit_price"])
            # 置信度：任一机型已确认则升级
            if row.get("confidence") == "confirmed":
                entry["confidence"] = "confirmed"

    lib_rows = []
    for entry in registry.values():
        lib_rows.append({
            **entry,
            "models":       "、".join(sorted(entry["models"])),
            "last_updated": TODAY,
        })

    return sorted(lib_rows, key=lambda r: (r["bom_bucket"], r["name"]))


def _parse_price(price_str) -> tuple[str, str]:
    if not price_str:
        return "", ""
    s = str(price_str).replace("元", "").strip()
    if "~" in s:
        parts = s.split("~")
        return parts[0].strip(), parts[1].strip()
    try:
        v = float(s)
        return str(v), str(v)
    except ValueError:
        return s, ""


def _make_id(bucket: str, name: str) -> str:
    import re
    clean = re.sub(r"[^\w]", "_", name)
    return f"{bucket[:8]}_{clean}"[:48]


# ── 主流程 ──────────────────────────────────────────────────────

def load_teardown_csv(csv_path: Path) -> list[dict]:
    """读取单个 teardown CSV，返回原始行列表（保留 confidence 来源字段）"""
    rows = []
    with csv_path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("name", "").strip():
                rows.append(row)
    return rows


def load_existing_lib() -> dict[str, dict]:
    """读取现有 components_lib.csv，返回以 id 为 key 的字典，用于价格字段合并。"""
    if not LIB_CSV.exists():
        return {}
    existing: dict[str, dict] = {}
    with LIB_CSV.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("id"):
                existing[row["id"]] = row
    return existing


def merge_prices(new_rows: list[dict], existing: dict[str, dict]) -> list[dict]:
    """将现有库中人工维护的 cost_min/cost_max 回填到重建结果，避免覆盖。"""
    for row in new_rows:
        prev = existing.get(row["id"])
        if not prev:
            continue
        # 只要旧库中有价格，无条件保留（人工维护优先）
        if prev.get("cost_min"):
            row["cost_min"] = prev["cost_min"]
        if prev.get("cost_max"):
            row["cost_max"] = prev["cost_max"]
    return new_rows


def main(csv_files: list[Path]):
    LIB_DIR.mkdir(exist_ok=True)
    all_rows: list[dict] = []

    try:
        from core.feishu_sync import sync_components_lib
    except ImportError:
        sync_components_lib = lambda *a, **kw: None

    for csv_path in csv_files:
        rows = load_teardown_csv(csv_path)
        print(f"  ✓ {csv_path.name}: {len(rows)} 条")
        all_rows.extend(rows)

    existing = load_existing_lib()
    lib = build_lib(all_rows)
    lib = merge_prices(lib, existing)

    price_preserved = sum(1 for r in lib if r.get("cost_min") and r["id"] in existing
                          and existing[r["id"]].get("cost_min") == r["cost_min"])
    print(f"  价格字段：{price_preserved} 条保留现有值，{len(lib) - price_preserved} 条从拆机数据填充")

    with open(LIB_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=LIB_FIELDS)
        w.writeheader()
        w.writerows(lib)
    print(f"\n标准件库 ({TODAY}): {len(lib)} 条 → {LIB_CSV}")

    buckets = Counter(r["bom_bucket"] for r in lib)
    for bucket, cnt in sorted(buckets.items()):
        print(f"  {BOM_BUCKET_CN.get(bucket, bucket):12s}  {cnt:3d} 条")

    sync_components_lib(lib)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        files = [Path(a) for a in sys.argv[1:] if Path(a).suffix == ".csv"]
    else:
        files = sorted(TEARDOWN_DIR.glob("*.csv"))
        if not files:
            print(f"{TEARDOWN_DIR} 目录下没有找到 CSV 文件")
            sys.exit(1)

    print(f"读取 {len(files)} 个 teardown CSV...")
    main(files)
