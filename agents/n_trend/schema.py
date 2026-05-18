"""N · 趋势分析师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "s_curve_analysis": {
    "industry_position":       "导入期/成长期/成熟期/衰退期",
    "industry_position_evidence": {
      "shipment_data":   str,    # 近 3~5 年中国/全球出货量数据点 (e.g. "2022 600万→2024 850万台")
      "asp_trend":       str,    # 均价走势 (e.g. "2022 ¥3200 → 2024 ¥2800")
      "spec_innovation": str     # 关键性能指标刷新速度 (吸力/续航/越障 1~2 年内 1.5x = 成长期, 持平 = 成熟期)
    },
    "subsystem_positions": [
      {
        "subsystem":             str,
        "position":              str,
        "evidence":              str,
        "evolution_data_3y":     str    # 近 3 年关键指标变化 (e.g. "LDS+视觉融合: 2022 仅旗舰 → 2024 全价位标配")
      }, ...
    ],
    "next_s_curve_seed":   str
  },
  "evolution_directions": [
    {
      "trend":               "理想化/动态化/可控性/集成化/智能化",
      "concrete_pathway":    str,
      "first_mover":         str,
      "first_mover_url":     str         # 首发产品/公告/专利 URL（可点击）；无则填 ""
    }, ...
  ],
  "four_new": {
    "new_material": [{"item": str, "evidence_source": str, "process_id_ref": str}, ...],
    "new_process":  [{"item": str, "evidence_source": str, "process_id_ref": str}, ...],  # process_id_ref 是否进入 processes.csv 工艺库
    "new_form":     [{"item": str, "evidence_source": str}, ...],
    "new_control":  [{"item": str, "evidence_source": str}, ...]
  },
  "innovation_roadmap_3y": [
    {"year": int, "milestone": str, "dependency": str}, ...  # dependency 指依赖哪个上游能力（4 新中的哪一条）
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
