"""
BOM数据加载器 - 从 CSV 解析扫地机器人拆机数据

CSV 格式（data/teardowns/*.csv）：
  列：bom_bucket, section, name, model, type, spec, manufacturer, unit_price, qty, confidence, product_source

  section 分类映射：
    PCB       → pcb_components
    电机       → motors
    传感器     → sensors
    结构/其他  → others

  model_key 取自文件名（去掉 _teardown*.csv 后缀），与 products_db.json 的 key 对应。
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

TEARDOWNS_DIR = Path(__file__).parent.parent / "data" / "teardowns"

_bom_cache: dict[str, dict[str, Any]] | None = None


def _model_key_from_file(path: Path) -> str:
    name = path.stem  # e.g. "石头G30SPro_teardown" or "石头G30SPro_teardown_2026-04-17"
    for suffix in ("_teardown", "_Teardown"):
        idx = name.find(suffix)
        if idx != -1:
            return name[:idx]
    return name


def _parse_csv(path: Path) -> dict[str, Any]:
    pcb: list[dict] = []
    motors: list[dict] = []
    sensors: list[dict] = []
    others: list[dict] = []

    with path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            section = (row.get("section") or "").strip()
            name    = (row.get("name")    or "").strip()
            model   = (row.get("model")   or "").strip()
            rtype   = (row.get("type")    or "").strip()
            spec    = (row.get("spec")    or "").strip()
            mfr     = (row.get("manufacturer") or "").strip()
            bucket  = (row.get("bom_bucket")   or "").strip()
            conf    = (row.get("confidence")   or "").strip()

            try:
                unit_price = float(row.get("unit_price") or 0) or None
            except ValueError:
                unit_price = None
            try:
                qty = int(float(row.get("qty") or 1))
            except ValueError:
                qty = 1

            if not name:
                continue

            if section == "PCB":
                pcb.append({
                    "board":      bucket,
                    "function":   name,
                    "model":      model,
                    "qty":        qty,
                    "manufacturer": mfr,
                    "spec":       spec,
                    "unit_price": unit_price,
                    "confidence": conf,
                })
            elif section == "电机":
                motors.append({
                    "name":         name,
                    "type":         rtype,
                    "model":        model,
                    "params":       spec,
                    "qty":          qty,
                    "manufacturer": mfr,
                    "unit_price":   unit_price,
                    "confidence":   conf,
                })
            elif section == "传感器":
                sensors.append({
                    "name":         name,
                    "type":         rtype,
                    "qty":          qty,
                    "manufacturer": mfr,
                    "unit_price":   unit_price,
                    "spec":         spec,
                    "confidence":   conf,
                })
            else:
                others.append({
                    "name":         name,
                    "type":         rtype,
                    "spec":         spec,
                    "manufacturer": mfr,
                    "unit_price":   unit_price,
                    "qty":          qty,
                    "bom_bucket":   bucket,
                    "confidence":   conf,
                })

    return {"pcb": pcb, "motors": motors, "sensors": sensors, "others": others}


def _load_all() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if not TEARDOWNS_DIR.exists():
        return result
    for csv_file in sorted(TEARDOWNS_DIR.glob("*.csv")):
        key = _model_key_from_file(csv_file)
        result[key] = _parse_csv(csv_file)
    return result


def get_bom_data() -> dict[str, dict[str, Any]]:
    """返回所有产品的拆机数据。data/teardowns/ 为空时返回空字典。"""
    global _bom_cache
    if _bom_cache is None:
        _bom_cache = _load_all()
    return _bom_cache


def get_models() -> list[str]:
    return list(get_bom_data().keys())
