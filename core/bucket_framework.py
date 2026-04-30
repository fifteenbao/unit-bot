"""
扫地机器人 BOM 8 桶成本分析框架加载器。

数据源: core/bom_8bucket_framework.json (版本化的标准模板, 与本模块同目录)
消费者: scripts/gen_teardown.py (拆机 BOM 生成), scripts/analyze_*.py (成本分析)

配套的 data/lib/bom_8bucket_framework.csv 是给人看/对账填价用的工作表,
不由本模块消费; 如模板有变, 用 scripts/export_framework_csv.py 重新生成。

提供:
  - load_framework(): 加载原始 JSON
  - buckets_ordered(): 按 order 返回 [(key, cn_name), ...]
  - bucket_pct_range(key): 返回 (low, high) 行业占比小数
  - render_prompt_bucket_section(): 生成给 LLM 的桶清单文本
  - audit_coverage(rows): 对一份 BOM 行检查每桶子项覆盖缺口
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

FRAMEWORK_FILE = Path(__file__).parent / "bom_8bucket_framework.json"


@lru_cache(maxsize=1)
def load_framework() -> dict:
    return json.loads(FRAMEWORK_FILE.read_text(encoding="utf-8"))


def buckets_ordered() -> list[tuple[str, str]]:
    """按 order 返回 [(key, name_cn), ...]"""
    fw = load_framework()
    items = sorted(fw["buckets"].items(), key=lambda kv: kv[1]["order"])
    return [(k, b["name_cn"]) for k, b in items]


def bucket_pct_range(key: str) -> tuple[float, float]:
    """返回 (low, high) 小数形式, 例如 (0.10, 0.15)"""
    b = load_framework()["buckets"][key]
    lo, hi = b["industry_pct_range"]
    return lo / 100.0, hi / 100.0


def bucket_pct_avg(key: str) -> float:
    """返回平均占比小数"""
    return load_framework()["buckets"][key]["industry_pct_avg"] / 100.0


def typical_item_names(key: str) -> list[str]:
    """返回某桶的典型子项名列表"""
    return [it["name"] for it in load_framework()["buckets"][key]["typical_items"]]


def typical_items_with_qty(key: str) -> list[tuple[str, int, str]]:
    """返回某桶 [(name, default_qty, mutex_group), ...]; mutex_group 缺省空字符串.

    mutex_group: 互斥组标记 (如 "mop_form" 表示双转盘/滚筒/履带三类拖布同组).
                  framework_fill 时, 组内任一已被覆盖则跳过组内其他, 避免补错形态.
    """
    return [
        (it["name"], int(it.get("default_qty", 1)), it.get("mutex_group", ""))
        for it in load_framework()["buckets"][key]["typical_items"]
    ]


def bucket_pct_tolerance() -> float:
    """占比偏差容忍度(百分点), 从 framework validation_rules 读取。"""
    return float(load_framework()["validation_rules"]["bucket_pct_tolerance"])


def expected_bom_msrp_ratio() -> tuple[float, float]:
    """BOM/MSRP 比例期望区间(百分比), 低于下限或高于上限视为异常。"""
    lo, hi = load_framework()["validation_rules"]["expected_bom_msrp_ratio_pct"]
    return float(lo), float(hi)


def bucket_boundary_notes(key: str) -> list[str]:
    """返回某桶的全部边界说明(prompt 应全量注入, 减少归错桶)。"""
    return list(load_framework()["buckets"][key].get("boundary_notes", []))


def bucket_definition(key: str) -> str:
    return load_framework()["buckets"][key]["definition"]


def render_prompt_bucket_section(include_example_spec: bool = True) -> str:
    """生成 LLM prompt 中的桶清单文本块, 含定义+典型子项+全部边界说明。

    重要: 每桶明确标注 bom_bucket 英文 key, LLM 必须使用该 key 而不是自创命名。
    include_example_spec=True 时每个子项附带典型规格, LLM 输出更精确。
    """
    fw = load_framework()
    lines: list[str] = []
    for bkey, b in sorted(fw["buckets"].items(), key=lambda kv: kv[1]["order"]):
        lo, hi = b["industry_pct_range"]
        lines.append(
            f"- **{b['order']}. {b['name_cn']}** "
            f"(bom_bucket=`{bkey}`, 基准占比 {b['industry_pct_avg']}% "
            f"[合格区间 {lo}-{hi}%])"
        )
        lines.append(f"  定义: {b['definition']}")
        if include_example_spec:
            last_section = None
            for it in b["typical_items"]:
                section = it.get("section", "")
                if section and section != last_section:
                    lines.append(f"    【{section}】")
                    last_section = section
                spec = it.get("example_spec", "")
                lines.append(f"    · {it['name']}" + (f" — {spec}" if spec else ""))
        else:
            items = "、".join(it["name"] for it in b["typical_items"])
            lines.append(f"  典型子项: {items}")
        for note in b.get("boundary_notes", []):
            lines.append(f"  边界: {note}")
        lines.append("")
    valid_keys = ", ".join(f"`{k}`" for k in bucket_keys())
    lines.append(
        f"⚠ **`bom_bucket` 字段必须严格使用以下 8 个 key 之一**: {valid_keys}。"
        f"不要自创命名 (如 perception_system / actuation_drive / cleaning_function 等)。"
    )
    return "\n".join(lines).rstrip()


def bucket_keys() -> list[str]:
    fw = load_framework()
    return [k for k, _ in sorted(fw["buckets"].items(), key=lambda kv: kv[1]["order"])]


def audit_coverage(rows: list[dict], bucket_field: str = "bom_bucket",
                   name_field: str = "name") -> dict:
    """
    对照 framework 的 typical_items, 检查每桶覆盖缺口。
    返回 {bucket: {"count": n, "present": [...], "missing": [...], "status": "✓/△/⚠"}}。

    覆盖判定: typical_item 的 name 关键词 (取前 4 字) 出现在任意行的 name 中即算 present。
    """
    fw = load_framework()
    result: dict[str, dict] = {}

    # 按桶归集行
    by_bucket: dict[str, list[dict]] = {k: [] for k in fw["buckets"]}
    for r in rows:
        b = (r.get(bucket_field) or "").strip()
        if b in by_bucket:
            by_bucket[b].append(r)

    for bkey, bdef in fw["buckets"].items():
        bucket_rows = by_bucket[bkey]
        names_blob = " ".join((r.get(name_field) or "") for r in bucket_rows)
        present, missing = [], []
        for it in bdef["typical_items"]:
            # 取子项名前 4 字作为关键词 (避免"主控 SoC" vs "SoC" 这种漏匹)
            key_frag = it["name"].replace(" ", "").replace("/", "")[:4]
            if key_frag and key_frag in names_blob.replace(" ", ""):
                present.append(it["name"])
            else:
                missing.append(it["name"])

        count = len(bucket_rows)
        if count == 0:
            status = "⚠ 无数据"
        elif len(missing) > len(bdef["typical_items"]) * 0.6:
            status = f"△ 覆盖不全 ({len(present)}/{len(bdef['typical_items'])})"
        else:
            status = f"✓ 覆盖 {len(present)}/{len(bdef['typical_items'])}"

        result[bkey] = {
            "name_cn": bdef["name_cn"],
            "count": count,
            "present": present,
            "missing": missing,
            "pct_avg": bdef["industry_pct_avg"],
            "status": status,
        }
    return result


def level1_validation() -> dict:
    """返回一级成本大类的 pct_range 校验规则。"""
    return load_framework()["validation_rules"].get("level1_pct_validation", {})


def level1_reference_costs() -> dict:
    """返回一级成本大类的描述与参考成本区间。"""
    return load_framework()["teardown_hierarchy"]["level1_categories"]


def estimate_level1_costs(hardware_bom_cny: float, msrp: float = 0) -> dict:
    """根据硬件 BOM 实测值 + 固定参考成本估算整机全成本。

    核心逻辑: 非硬件成本(人工/物流/研发均摊/销售管理)单台相对固定，不随 BOM 波动。
    硬件物料是唯一高度可变的成本项。

    segment 判定:
      - msrp ≥ 4000 → flagship
      - msrp ≥ 2000 → mid
      - 其余 → entry

    返回 {name: {cost, pct, source}, ...}，含 '整机全成本 (估算)' 汇总行。
    """
    l1c = level1_reference_costs()
    if not l1c:
        return {}

    # 判定档位
    if msrp >= 4000:
        segment = "flagship"
    elif msrp >= 2000:
        segment = "mid"
    else:
        segment = "entry"

    # 非硬件成本: 从 reference_cost 取对应档位值 (固定, 不随 BOM 波动)
    fixed_costs: dict[str, float] = {}
    for name in ["人工+机器折旧", "销售+管理费用", "研发均摊", "仓储物流售后"]:
        ref = l1c.get(name, {}).get("reference_cost", {})
        fixed_costs[name] = float(ref.get(segment, 0))

    fixed_total = sum(fixed_costs.values())
    total_estimated = hardware_bom_cny + fixed_total

    result = {}
    result["硬件物料 (7桶)"] = {
        "cost": round(hardware_bom_cny, 0),
        "pct": round(hardware_bom_cny / total_estimated * 100, 1) if total_estimated else 0,
        "source": "BOM 实测",
        "note": "★ 唯一高度可变项，随功能配置差异显著",
    }

    for name in ["人工+机器折旧", "销售+管理费用", "研发均摊", "仓储物流售后"]:
        cost = fixed_costs[name]
        result[name] = {
            "cost": round(cost, 0),
            "pct": round(cost / total_estimated * 100, 1) if total_estimated else 0,
            "source": f"{segment}档 固定参考",
            "note": "单台成本相对固定，不随 BOM 波动",
        }

    result["整机全成本 (估算)"] = {
        "cost": round(total_estimated, 0),
        "pct": 100.0,
        "source": "",
        "segment": segment,
    }

    return result


def sensor_tiers() -> dict:
    """返回感知桶的高/中/低三档传感器方案定义。"""
    return load_framework()["buckets"]["perception"].get("sensor_tiers", {})


def detect_sensor_tier(bom_rows: list[dict]) -> str:
    """从 BOM 行中检测产品的传感器档位。

    检测规则:
      - 高配: 包含 结构光/dToF/视觉摄像头/AI加速器 任一
      - 中配: 包含 激光雷达/LDS/ToF
      - 低配: 仅包含 IMU/碰撞/地检 等基础传感器

    返回 "high" / "mid" / "low"。
    """
    names_blob = " ".join(
        (r.get("name") or "") + " " + (r.get("spec") or "")
        for r in bom_rows
    )
    if any(kw in names_blob for kw in ["结构光", "dToF", "视觉摄像", "AI加速", "RGB摄像", "NPU"]):
        return "high"
    if any(kw in names_blob for kw in ["激光雷达", "LDS", "ToF", "TOF", "线激光"]):
        return "mid"
    return "low"
