"""A · 裁剪策略师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "trim_decisions": [
    {
      "trim_level":          "一级/二级/三级",
      "target":              str,
      "saved_cny":           int,
      "compensation":        str,
      "risk_assessment":     str,
      "evidence_from_function_model": str
    }, ...
  ],
  "technical_contradictions": [
    {
      "param_to_improve":     str,
      "param_that_worsens":   str,
      "candidate_principles": [str, ...],   # TRIZ 40 发明原理
      "concrete_proposal":    str
    }, ...
  ],
  "physical_contradictions": [
    {
      "param":              str,
      "opposite_demands":   [str, str],
      "separation_method":  "时间/空间/条件/系统",
      "concrete_proposal":  str
    }, ...
  ],
  "architectural_bottlenecks": [
    {"description": str, "needs_n_stage": bool}, ...
  ],
  "total_saved_cny": int,
  "summary": str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型：{product_key}\n\n"
        "请按 A 阶段【裁剪策略师】职责，给出三级裁剪决策清单 + "
        "TRIZ 技术/物理矛盾分析 + 架构瓶颈识别。"
        "完成后只输出一段 ```json 代码块。"
    )
