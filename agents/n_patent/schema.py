"""N · 专利规避师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "patent_landscape": [
    {
      "key_player":      str,
      "patent_density":  "高/中/低",
      "key_patent_areas": [str, ...]
    }, ...
  ],
  "risk_patents": [
    {
      "patent_id":          str,
      "title":              str,
      "key_claims":         [str, ...],
      "match_to_candidate": "完全相同/等同/实质不同",
      "risk_level":         "高/中/低"
    }, ...
  ],
  "design_around_options": [
    {
      "strategy":          "替换技术手段/改变结构特征/改变实施场景/不做该功能",
      "concrete_change":   str,
      "lost_capability":   str,
      "engineering_cost":  "低/中/高",
      "residual_risk":     str
    }, ...
  ],
  "needs_lawyer_review": [
    {"item": str, "reason": str}, ...
  ],
  "summary": str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型：{product_key}\n\n"
        "请按 N 阶段【专利规避师】职责，对 /fos 候选方案做专利检索 + 权利要求映射 + "
        "工程层规避方案。**法律意见留给律师。**"
        "完成后只输出一段 ```json 代码块。"
    )
