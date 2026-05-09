"""S · 平台架构师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "complexity_assessment": {
    "sku_count":              int,
    "shared_parts_rate":      float,        # 0~1
    "platformization_score":  float,        # 0~1
    "complexity_score":       float,        # 0~1, 越高越复杂
    "complexity_evidence":    str
  },
  "platform_candidates": [
    {
      "subsystem":            str,
      "rationale":            str,
      "frequency":            "高/中/低",
      "cross_model_variance": "高/中/低",
      "roi_priority":         "高/中/低"
    }, ...
  ],
  "platform_designs": [
    {
      "platform_name":       str,
      "covers_models":       [str, ...],
      "variable_params":     [str, ...],
      "interface_standards": [str, ...],
      "expected_roi":        str
    }, ...
  ],
  "complexity_process":      [str, ...],
  "summary":                 str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型（作为切入视角，但要看整个产品矩阵）：{product_key}\n\n"
        "请按 S 阶段【平台架构师】职责，做产品复杂性评分、平台化候选识别、"
        "具体平台设计、复杂性管理流程建议。完成后只输出一段 ```json 代码块。"
    )
