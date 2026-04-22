"""
标准件库 — 读写 data/lib/components_lib.csv

CSV 字段：
  id, bom_bucket, bom_bucket_cn, name, name_en, tier, model_numbers,
  spec, cost_min, cost_max, unit, suppliers, confidence, models, last_updated
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

LIB_FILE = Path(__file__).parent.parent / "data" / "lib" / "components_lib.csv"

LIB_FIELDS = [
    "id", "bom_bucket", "bom_bucket_cn", "name", "name_en",
    "tier", "model_numbers", "spec", "cost_min", "cost_max", "unit",
    "suppliers", "confidence", "models", "last_updated",
]

CATEGORY_NAMES = {
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


# ── 读写 ────────────────────────────────────────────────────────

def load_lib() -> list[dict]:
    """返回所有条目列表，每条为 CSV 行字典。文件不存在时返回空列表。"""
    if not LIB_FILE.exists():
        return []
    with LIB_FILE.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def save_lib(rows: list[dict]) -> None:
    LIB_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LIB_FILE.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=LIB_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ── CRUD ────────────────────────────────────────────────────────

def upsert_component(comp_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """新增或更新（按 id 匹配第一条）。返回写入后的行字典。"""
    rows = load_lib()
    today = date.today().isoformat()

    for i, row in enumerate(rows):
        if row.get("id") == comp_id:
            row.update({k: v for k, v in data.items() if k in LIB_FIELDS})
            row["last_updated"] = today
            rows[i] = row
            save_lib(rows)
            return row

    # 新增
    new_row: dict = {f: "" for f in LIB_FIELDS}
    new_row["id"] = comp_id
    new_row["last_updated"] = today
    new_row.update({k: v for k, v in data.items() if k in LIB_FIELDS})
    rows.append(new_row)
    save_lib(rows)
    return new_row


def get_component(comp_id: str) -> dict[str, Any] | None:
    for row in load_lib():
        if row.get("id") == comp_id:
            return row
    return None


def list_components(
    category: str | None = None,
    tier: str | None = None,
    keyword: str | None = None,
) -> list[dict]:
    result = []
    for row in load_lib():
        if category and row.get("bom_bucket") != category:
            continue
        if tier and row.get("tier") != tier:
            continue
        if keyword:
            kw = keyword.lower()
            searchable = " ".join([
                row.get("name", ""),
                row.get("name_en", ""),
                row.get("model_numbers", ""),
                row.get("spec", ""),
                row.get("suppliers", ""),
            ]).lower()
            if kw not in searchable:
                continue

        cost_min = row.get("cost_min", "")
        cost_max = row.get("cost_max", "")
        cost_range = f"¥{cost_min}~{cost_max}" if cost_min else "待定"

        result.append({
            "id":           row.get("id", ""),
            "name":         row.get("name", ""),
            "bom_bucket":   row.get("bom_bucket", ""),
            "category":     CATEGORY_NAMES.get(row.get("bom_bucket", ""), row.get("bom_bucket_cn", "")),
            "tier":         TIER_NAMES.get(row.get("tier", ""), row.get("tier", "")),
            "model_numbers": row.get("model_numbers", ""),
            "spec":         row.get("spec", ""),
            "bom_cost_range": cost_range,
            "suppliers":    row.get("suppliers", ""),
            "confidence":   row.get("confidence", ""),
            "models":       row.get("models", ""),
        })
    return result


def delete_component(comp_id: str) -> bool:
    rows = load_lib()
    new_rows = [r for r in rows if r.get("id") != comp_id]
    if len(new_rows) == len(rows):
        return False
    save_lib(new_rows)
    return True


def init_standard_library(force: bool = False) -> int:
    """CSV 已存在且非空时跳过（不覆盖人工维护数据）。返回现有条目数。"""
    rows = load_lib()
    if rows and not force:
        return len(rows)
    return 0
