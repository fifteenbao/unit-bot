"""L · DFM 优化师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "dfm_proposals": [
    {
      "lever_id": int,                 # 1..5 对应 5 项优化方向
      "lever_name": str,
      "target_part": str,
      "current_spec": str,
      "proposed_spec": str,
      "saved_cny": int,
      "risk": str,
      "process_constraint": str
    }, ...
  ],
  "should_cost_analysis": [
    {
      "part":          str,
      "material_cost": float,
      "process_cost":  float,
      "fair_profit":   float,
      "should_cost":   float,
      "current_price": float,
      "gap_cny":       float,            # current_price - should_cost
      "negotiation_priority": "高/中/低"
    }, ...
  ],
  "total_saved_cny": int,
  "summary": str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型：{product_key}\n\n"
        "请按 L 阶段【DFM 优化师】职责，给出 5 项材料/工艺优化提案 + "
        "3~5 个核心件的应该成本（Should Cost）建模。"
        "完成后只输出一段 ```json 代码块。"
    )
