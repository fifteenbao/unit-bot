"""
DFMA 辅助物料标准化成本模块 + 桶兜底价机制

用于自动补全拆机报告中未明确列出的小零件、辅助件、耗材等。
价格为 1k~10k 批量估算价（人民币，元/个）。

消费者:
  - core/bom_rules.py (通过 aux_price() 查辅料单价)
  - scripts/gen_teardown.py (Stage 4 分级查价, 辅料走 aux 兜底)
  - agent.py /dfma 命令 (通过 estimate_auxiliary_cost() 评估装配影响)
"""

from typing import Any

# ====================== 价格常量 ======================

AUX_PRICE = {
    "micro": 0.10,      # 极小件：贴纸、铭牌、丝印、标签、胶点
    "tiny":  0.30,      # 微小紧固件：螺丝、螺母、垫片、O型圈、卡扣小爪
    "small": 0.80,      # 小型辅助件：硅胶脚垫、泡棉密封条、小支架、线卡、固定夹
    "mid":   2.00,      # 中型件：普通注塑小零件、短连接线、软管、水路接头、密封圈
    "large": 5.00,      # 大型辅助结构件：大盖板、长风道、底盘加强筋、较大支架
}

# 辅助件默认数量建议（可根据桶类型动态调整）
DEFAULT_AUX_QTY = {
    "micro": 8,   # 贴纸类通常较多
    "tiny":  12,  # 螺丝类数量最多
    "small": 6,
    "mid":   4,
    "large": 2,
}

# DFMA 辅助件分类与装配影响
AUX_DFMA_IMPACT = {
    "micro": {"assembly_difficulty": 1, "part_count_weight": 0.5},
    "tiny":  {"assembly_difficulty": 2, "part_count_weight": 1.0},   # 紧固件对 DFA 影响最大
    "small": {"assembly_difficulty": 2, "part_count_weight": 0.8},
    "mid":   {"assembly_difficulty": 3, "part_count_weight": 1.2},
    "large": {"assembly_difficulty": 4, "part_count_weight": 2.0},
}


def estimate_auxiliary_cost(bom_bucket: str, part_count: int = 0) -> dict[str, Any]:
    """
    根据桶类型和已有零件数，估算辅助件成本。
    已有零件越多，辅助件相对越少（避免重复计算）。
    返回：总辅助成本、预计零件数增量、装配难度增量。
    """
    bucket_multiplier = {
        "structure_cmf":       1.45,
        "cleaning":            1.25,
        "power_motion":        1.1,
        "dock_station":        1.35,
    }.get(bom_bucket, 1.0)

    total_aux_cost = 0.0
    total_aux_parts = 0

    for aux_type, price in AUX_PRICE.items():
        base_qty = DEFAULT_AUX_QTY[aux_type]
        adjusted_qty = max(2, int(base_qty * bucket_multiplier * (1 - part_count * 0.015)))
        cost = price * adjusted_qty
        total_aux_cost += cost
        total_aux_parts += adjusted_qty

    difficulty_increase = sum(
        AUX_DFMA_IMPACT[t]["assembly_difficulty"] * DEFAULT_AUX_QTY[t]
        for t in AUX_PRICE
    ) * bucket_multiplier * 0.1

    return {
        "aux_cost": round(total_aux_cost, 2),
        "aux_part_count": total_aux_parts,
        "assembly_difficulty_increase": round(difficulty_increase, 1),
        "suggestion": "优先用卡扣/磁吸替代螺丝（tiny类），可降辅助零件数 15-30%",
    }


def get_bucket_default_price(bucket: str, part_count: int = 0) -> dict[str, Any]:
    """获取桶兜底价 + 最小兜底 + 告警。

    返回每件兜底价、该桶最低总成本下限、以及是否需要告警。
    当某桶大量零件走兜底价时，用此函数确保不严重低估。
    """
    from core.bom_rules import BUCKET_DEFAULT_PRICE, BUCKET_MIN_FLOOR_COST  # noqa: E402

    default_per_part = BUCKET_DEFAULT_PRICE.get(bucket, 2.0)
    min_floor = BUCKET_MIN_FLOOR_COST.get(bucket, 15)

    estimated = default_per_part * max(5, part_count)
    final_floor_cost = max(estimated, min_floor)

    warning = "【兜底价告警】" if part_count > 0 and estimated < min_floor else ""

    return {
        "default_per_part": default_per_part,
        "final_floor_cost": round(final_floor_cost, 2),
        "warning": warning,
        "suggestion": f"{bucket} 桶建议优先补充 components_lib.csv 数据",
    }
