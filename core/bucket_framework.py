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


def detect_product_features(specs: dict | None, notes: str = "") -> dict[str, bool]:
    """从产品 specs + notes 检测硬件功能特性标志。

    返回 {feature_flag: True/False, ...}，用于过滤 framework 中带 condition 的典型子项。
    """
    s = specs or {}
    n = (notes or "").lower()
    return {
        # 基站存在性 (auto_empty/auto_wash/self_cleaning 任一为 True 则有机站)
        "has_dock": (
            s.get("auto_empty") is True
            or s.get("auto_wash") is True
            or s.get("self_cleaning") is True
        ),
        # 自动集尘
        "auto_empty": s.get("auto_empty") is True,
        # 基站自清洁 (洗拖布)
        "auto_wash": s.get("auto_wash") is True,
        # 热风烘干
        "hot_air_dry": s.get("hot_air_dry") is True,
        # 拖布抬升
        "mop_lift": s.get("mop_lift") is True,
        # 自动上下水 (从 notes 检测)
        "auto_water": "上下水" in n,
        # 升降雷达 (从 notes 检测)
        "lift_radar": "升降雷达" in n or "雷达升降" in n,
        # 拖布延边 / 机械臂 (从 notes 检测)
        "mop_extend": any(k in n for k in ("延边", "机械臂", "伸缩拖布")),
        # 履带驱动 (从 notes 检测)
        "track_drive": "履带" in n,
        # 越障底盘升降 (从 notes 或 specs 检测)
        "obstacle_lift": "越障" in n or (s.get("obstacle_height_cm") or 0) >= 4,
        # 导航类型
        "nav_lidar": s.get("navigation", "") in ("激光导航", "LDS"),
        "nav_rgb": s.get("navigation", "") in ("RGB", "双目", "双目RGB"),
        "nav_ai": s.get("navigation", "") in ("GPT大模型", "AI"),
    }


def _is_item_applicable(item: dict, features: dict[str, bool] | None) -> bool:
    """检查 typical_item 是否对当前产品适用 (condition 字段过滤)。

    condition 语法:
      - "flag"           → features["flag"] 为 True 时包含
      - "!flag"          → features["flag"] 为 False 时包含
      - "a,b"            → a AND b (都为 True 才包含)
      - "a|b"            → a OR b (任一为 True 即包含)
      - "a|b,c"          → (a OR b) AND c (| 优先级高于 ,)
    """
    if not features:
        return True
    cond = item.get("condition", "").strip()
    if not cond:
        return True
    # 按逗号拆 AND 组, 每组内按 | 拆 OR
    for and_part in cond.split(","):
        and_part = and_part.strip()
        if not and_part:
            continue
        or_parts = [p.strip() for p in and_part.split("|") if p.strip()]
        if not or_parts:
            continue
        or_match = False
        for p in or_parts:
            if p.startswith("!"):
                if not features.get(p[1:], False):
                    or_match = True
                    break
            else:
                if features.get(p, False):
                    or_match = True
                    break
        if not or_match:
            return False
    return True


def _get_applicable_items(key: str, features: dict[str, bool] | None) -> list[dict]:
    """返回某桶所有满足 condition 的 typical_items (按 product features 过滤)。"""
    # 桶级 gate: 无基站产品跳过整个 dock_station 桶
    if features and key == "dock_station" and not features.get("has_dock"):
        return []
    items = load_framework()["buckets"][key]["typical_items"]
    return [it for it in items if _is_item_applicable(it, features)]


def typical_item_names(key: str, features: dict[str, bool] | None = None) -> list[str]:
    """返回某桶的典型子项名列表 (按 product features 过滤不适用项)。"""
    return [it["name"] for it in _get_applicable_items(key, features)]


def typical_items_with_qty(key: str, features: dict[str, bool] | None = None
                           ) -> list[tuple[str, int, str]]:
    """返回某桶 [(name, default_qty, mutex_group), ...]; mutex_group 缺省空字符串.

    mutex_group: 互斥组标记 (如 "mop_form" 表示双转盘/滚筒/履带三类拖布同组).
                  framework_fill 时, 组内任一已被覆盖则跳过组内其他, 避免补错形态.
    """
    return [
        (it["name"], int(it.get("default_qty", 1)), it.get("mutex_group", ""))
        for it in _get_applicable_items(key, features)
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


def _tokenize(name: str) -> set[str]:
    """拆名称为 token 集合 (按分隔符切分, 滤掉过短的)。"""
    tokens = re.split(r"[/\-\·,、()（）\s]+", (name or "").lower())
    return {t for t in tokens if len(t) >= 2}


def audit_coverage(rows: list[dict], bucket_field: str = "bom_bucket",
                   name_field: str = "name",
                   features: dict[str, bool] | None = None) -> dict:
    """
    对照 framework 的 typical_items, 检查每桶覆盖缺口。
    返回 {bucket: {"count": n, "present": [...], "missing": [...], "status": "✓/△/⚠"}}。

    覆盖判定: framework 子项名拆为 token 集合, 与桶内各行名的 token 集合做交集;
              交集 ≥ 子项 token 数 50% 即算 present。
              (解决 "ROM / eMMC" vs "eMMC / ROM" 之类 token 顺序不一致问题)
    features: detect_product_features() 输出, 用于过滤带 condition 的典型子项。
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
        applicable = _get_applicable_items(bkey, features)
        # 每行预 tokenize
        row_token_sets = [_tokenize(r.get(name_field) or "") for r in bucket_rows]
        present, missing = [], []
        for it in applicable:
            it_tokens = _tokenize(it["name"])
            if not it_tokens:
                missing.append(it["name"])
                continue
            # 50% 以上 token 命中任意一行即算 present
            matched = False
            for row_tokens in row_token_sets:
                overlap = it_tokens & row_tokens
                if len(overlap) >= max(1, len(it_tokens) * 0.5):
                    matched = True
                    break
            if matched:
                present.append(it["name"])
            else:
                missing.append(it["name"])

        count = len(bucket_rows)
        total_applicable = len(applicable)
        if total_applicable == 0:
            status = "— 不适用 (无该功能)"
        elif count == 0:
            status = "⚠ 无数据"
        elif len(missing) > total_applicable * 0.6:
            status = f"△ 覆盖不全 ({len(present)}/{total_applicable})"
        else:
            status = f"✓ 覆盖 {len(present)}/{total_applicable}"

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
