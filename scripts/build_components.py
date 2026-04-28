"""
拆机 / FCC CSV → 标准件库构建工具

读取以下两类数据源，汇总重建 data/lib/components_lib.csv：
  1. data/teardowns/*.csv               — gen_teardown 产出的整机拆机 CSV
  2. data/teardowns/fcc/*/*_fcc_*.csv   — fetch_fcc.py ocr 产出的 FCC 上游 CSV（直通）

【数据治理：置信度白名单】
  标准件库是"权威数据"，只接受高置信度来源：
    ✓ confirmed  人工/实物核实
    ✓ teardown   实物拆机 CSV
    ✓ fcc        FCC 文档 OCR 识别（监管申报材料，可靠）
    ✗ inferred / estimate / web — 直接丢弃，不污染权威库

  因此：FCC 数据可以**直接**跑 build_components 入库，无需先经 gen_teardown
  （gen_teardown 输出包含 Stage 2 启发式推导的 inferred 行，会被白名单过滤掉）。

用法：
  python scripts/build_components.py                                  # 读取所有 teardowns + fcc CSV
  python scripts/build_components.py data/teardowns/fcc/石头G30SPro/  # 只重建该机型 FCC 数据
  python scripts/build_components.py data/teardowns/某机型_teardown.csv  # 单文件
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
FCC_DIR      = TEARDOWN_DIR / "fcc"
LIB_DIR      = DATA_DIR / "lib"
LIB_CSV      = LIB_DIR / "components_lib.csv"

TODAY = date.today().isoformat()  # e.g. "2026-04-17"

# 标准件库置信度白名单：只允许高可信来源进入权威库
TRUSTED_CONFIDENCE = {"confirmed", "teardown", "fcc"}

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

def load_teardown_csv(csv_path: Path) -> tuple[list[dict], int]:
    """
    读取单个 CSV（teardown 或 FCC 上游），按 TRUSTED_CONFIDENCE 白名单过滤。
    返回 (通过白名单的行, 被丢弃的行数)。
    """
    rows: list[dict] = []
    dropped = 0
    with csv_path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not row.get("name", "").strip():
                continue
            conf = (row.get("confidence") or "").strip().lower()
            # FCC 上游 CSV 默认置信度视为 fcc（即使字段缺失）
            if not conf and "/fcc/" in str(csv_path).replace("\\", "/"):
                conf = "fcc"
                row["confidence"] = "fcc"
            if conf not in TRUSTED_CONFIDENCE:
                dropped += 1
                continue
            rows.append(row)
    return rows, dropped


def collect_csv_files() -> list[Path]:
    """收集所有合法输入：data/teardowns/*.csv + data/teardowns/fcc/*/*_fcc_*.csv。"""
    teardown_csvs = sorted(TEARDOWN_DIR.glob("*.csv"))
    fcc_csvs = sorted(FCC_DIR.glob("*/*_fcc_*.csv")) if FCC_DIR.exists() else []
    return teardown_csvs + fcc_csvs


def expand_path(arg: Path) -> list[Path]:
    """命令行参数：文件 → 单文件；目录 → 目录下所有 *.csv。"""
    if arg.is_file() and arg.suffix == ".csv":
        return [arg]
    if arg.is_dir():
        return sorted(arg.glob("*.csv"))
    return []


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
    total_dropped = 0
    src_stats: Counter = Counter()  # 按 confidence 统计被采纳的行数

    try:
        from core.feishu_sync import sync_components_lib
    except ImportError:
        sync_components_lib = lambda *a, **kw: None

    for csv_path in csv_files:
        rows, dropped = load_teardown_csv(csv_path)
        total_dropped += dropped
        for r in rows:
            src_stats[(r.get("confidence") or "").lower()] += 1
        tag = "FCC" if "/fcc/" in str(csv_path).replace("\\", "/") else "teardown"
        msg = f"  ✓ [{tag}] {csv_path.name}: {len(rows)} 条采纳"
        if dropped:
            msg += f"，{dropped} 条被白名单过滤"
        print(msg)
        all_rows.extend(rows)

    if total_dropped:
        print(f"\n  共过滤 {total_dropped} 条低置信度数据"
              f"（仅接受 {sorted(TRUSTED_CONFIDENCE)}）")
    if src_stats:
        print(f"  采纳来源分布: " + " · ".join(
            f"{src}={cnt}" for src, cnt in sorted(src_stats.items())
        ))

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
        files: list[Path] = []
        for a in sys.argv[1:]:
            files.extend(expand_path(Path(a)))
        if not files:
            print("未找到合法 CSV 输入（支持单文件或目录）")
            sys.exit(1)
    else:
        files = collect_csv_files()
        if not files:
            print(f"{TEARDOWN_DIR} 目录下没有找到 CSV 文件（含 fcc/ 子目录）")
            sys.exit(1)

    print(f"读取 {len(files)} 个 CSV (teardown + FCC)...")
    main(files)
