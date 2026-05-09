"""N · 趋势分析师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "s_curve_analysis": {
    "industry_position":   "导入期/成长期/成熟期/衰退期",
    "subsystem_positions": [
      {"subsystem": str, "position": str, "evidence": str}, ...
    ],
    "next_s_curve_seed":   str
  },
  "evolution_directions": [
    {
      "trend":            "理想化/动态化/可控性/集成化/智能化",
      "concrete_pathway": str,
      "first_mover":      str
    }, ...
  ],
  "four_new": {
    "new_material": [str, ...],
    "new_process":  [str, ...],
    "new_form":     [str, ...],
    "new_control":  [str, ...]
  },
  "innovation_roadmap_3y": [
    {"year": int, "milestone": str}, ...
  ],
  "summary": str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型（作为切入视角）：{product_key}\n\n"
        "请按 N 阶段【趋势分析师】职责，做 S 曲线分析、系统进化方向研判、"
        "四新设计机会清单、3 年创新路线图。完成后只输出一段 ```json 代码块。"
    )
