"""N · 功能创新搜索师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "fos_proposals": [
    {
      "original_function":         str,
      "abstract_description":      str,
      "cross_domain_inspiration":  [str, ...],
      "candidate_replacement":     str,
      "key_technologies":          [str, ...],
      "key_suppliers":             [str, ...],
      "integration_difficulty":    "低/中/高",
      "expected_cost_vs_current":  str,
      "risks":                     [str, ...]
    }, ...
  ],
  "summary": str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型：{product_key}\n\n"
        "请按 N 阶段【功能创新搜索师】职责，对 A 阶段识别的架构瓶颈做跨领域 FOS。"
        "完成后只输出一段 ```json 代码块。"
    )
