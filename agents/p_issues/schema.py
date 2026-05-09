"""P · 问题诊断师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "quality_issues": [
    {"phenomenon": str, "frequency": "高频/中频/低频",
     "impact": str, "evidence_source": str}, ...
  ],
  "service_issues": [
    {"area": "易耗品/维修/政策", "issue": str, "user_impact": str}, ...
  ],
  "improvement_opportunities": [
    {"opportunity": str, "category": "结构性/工艺性/供应链/预期错配"}, ...
  ],
  "summary": str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型：{product_key}\n\n"
        "请按 P 阶段【问题诊断师】职责，搜集质量问题清单、维修维护痛点、"
        "识别改善机会方向（不要给解决方案）。完成后只输出一段 ```json 代码块。"
    )
