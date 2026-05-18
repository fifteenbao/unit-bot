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
      "patent_id":          str,        # 标准格式 CN.../US.../WO.../EP...
      "patent_url":         str,        # 可点击链接（Google Patents/智慧芽/CNIPA），必填
      "patent_date":        str,        # 申请日或公开日 YYYY-MM-DD，影响剩余有效期
      "jurisdiction":       str,        # CN / US / EU / WO / JP / KR — 多地区用逗号
      "title":              str,
      "key_claims":         [str, ...],
      "match_to_candidate": "完全相同/等同/实质不同",
      "evidence_from_fos":  str,        # 必填：引用 fos.fos_proposals[i].candidate_replacement
      "risk_level":         "高/中/低",
      "remaining_years":    int         # 剩余有效期估算（专利 20 年 - 当前距申请日年数），未知填 -1
    }, ...
  ],
  "design_around_options": [
    {
      "strategy":          "替换技术手段/改变结构特征/改变实施场景/不做该功能",
      "concrete_change":   str,
      "lost_capability":   str,
      "engineering_cost":  "低/中/高",
      "residual_risk":     str,
      "evidence_from_fos": str          # 必填：所对应的 fos 提案
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
