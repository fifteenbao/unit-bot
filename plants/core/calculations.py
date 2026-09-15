"""Deterministic engineering calculations. All amounts use the stated currency."""
from __future__ import annotations

import math


def number(data, key, *, positive=False, maximum=None):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{key} 必须是有限数值，未知值不可用于计算")
    if value < 0 or (positive and value == 0) or (maximum is not None and value > maximum):
        raise ValueError(f"{key} 超出有效范围")
    return value


def calculate(kind, inputs):
    if not isinstance(inputs, dict):
        raise ValueError("计算 inputs 必须是对象")
    if kind not in CONTRACTS:
        raise ValueError(f"未知计算类型：{kind}")
    if set(inputs) != set(CONTRACTS[kind]["inputs"]):
        raise ValueError(f"{kind} 参数必须为：{', '.join(CONTRACTS[kind]['inputs'])}")
    if kind != "commonality":
        if not isinstance(inputs.get("currency"), str) or not inputs["currency"].strip():
            raise ValueError("必须声明 currency")
    if kind == "should_cost":
        good_units = number(inputs, "production_units", positive=True)
        cavities = number(inputs, "cavities", positive=True)
        if int(cavities) != cavities or int(good_units) != good_units:
            raise ValueError("production_units 与 cavities 必须是整数")
        yield_rate = number(inputs, "yield_rate", positive=True, maximum=1)
        material = number(inputs, "material_mass_kg") * number(inputs, "material_price_per_kg") / yield_rate
        process = number(inputs, "cycle_sec") * number(inputs, "hourly_rate") / 3600 / cavities / yield_rate
        mold = number(inputs, "mold_total") / good_units
        tooling = number(inputs, "tooling_total") / good_units
        base = material + process + mold + tooling
        rate = number(inputs, "profit_rate")
        basis = inputs.get("profit_basis")
        if basis not in ("markup", "margin") or (basis == "margin" and rate >= 1):
            raise ValueError("profit_basis 为 markup 或 margin；销售毛利率必须小于 1")
        total = base * (1 + rate) if basis == "markup" else base / (1 - rate)
        return {"currency": inputs["currency"], "unit": "per_good_unit",
                "material": material, "process": process, "mold": mold, "tooling": tooling,
                "profit": total - base, "should_cost": total,
                "formula": "(mass_kg*price_kg/yield + cycle_s*rate_h/3600/cavities/yield + (mold+tooling)/good_units) * (1+markup) or /(1-margin)"}
    if kind == "assembly":
        before = number(inputs, "before_seconds")
        after = number(inputs, "after_seconds")
        rate = number(inputs, "hourly_rate")
        return {"currency": inputs["currency"], "saved_seconds": before - after,
                "before_cost": before * rate / 3600, "after_cost": after * rate / 3600,
                "saved_per_unit": (before - after) * rate / 3600,
                "formula": "(before_seconds-after_seconds)*hourly_rate/3600"}
    if kind == "roi":
        before = number(inputs, "baseline_unit_cost")
        after = number(inputs, "proposed_unit_cost")
        volume = number(inputs, "annual_volume")
        investment = number(inputs, "investment")
        recurring = number(inputs, "annual_recurring_cost")
        annual = (before - after) * volume - recurring
        return {"currency": inputs["currency"], "annual_net_saving": annual,
                "first_year_net_benefit": annual - investment,
                "payback_years": investment / annual if annual > 0 else None,
                "annual_roi": annual / investment if investment > 0 else None,
                "formula": "annual_net=(baseline-proposed)*annual_volume-recurring; payback=investment/annual_net"}
    shared = number(inputs, "shared_unique_parts")
    total = number(inputs, "total_unique_parts", positive=True)
    if shared > total or int(shared) != shared or int(total) != total:
        raise ValueError("共件计数必须为整数，分子不大于分母")
    return {"commonality_rate": shared / total,
            "formula": "shared_unique_parts/total_unique_parts"}


CONTRACTS = {
    "should_cost": {
        "inputs": ["currency", "material_mass_kg", "material_price_per_kg", "cycle_sec", "hourly_rate",
                   "cavities", "yield_rate", "production_units", "mold_total", "tooling_total", "profit_basis", "profit_rate"],
        "notes": "质量为每模穴每次投料 kg（含流道等分摊）；yield 是良品比例。周期为整模秒数、费率为整机每小时费率。模具/工具总额按计划良品总量摊销，不再除模穴。只支持单工序；复杂工序应分别核算，禁止重复良率摊分。利润口径 markup=成本加成、margin=销售毛利。"},
    "assembly": {"inputs": ["currency", "before_seconds", "after_seconds", "hourly_rate"],
                 "notes": "同一产品单件前后装配秒数和同口径费率；可输出负节省。"},
    "roi": {"inputs": ["currency", "baseline_unit_cost", "proposed_unit_cost", "annual_volume", "investment", "annual_recurring_cost"],
            "notes": "静态、未折现 ROI；年度净节省非正时回收期为 null。"},
    "commonality": {"inputs": ["shared_unique_parts", "total_unique_parts"],
                    "notes": "产品族内至少两个型号共用的唯一零件数 / 产品族零件并集，需附统计范围与版本证据。"},
}
