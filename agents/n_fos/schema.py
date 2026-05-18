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
      "cost_evidence":             str,    # 必填：引用 dfm.should_cost_analysis 或 query_processes/molds 给出成本依据
      "process_id_candidate":      str,    # 新方案对应的 process_id（如改用 P_INJ_DOUBLE 共模、P_STAMP 钣金代替 CNC），无则填 ""
      "evidence_from_trim":        str,    # 必填：引用 trim.architectural_bottlenecks[i] 或 trim.trim_decisions[i]
      "user_pain_ref":             str,    # 必填：引用 research.mvp_pains[i] 或 issues.quality_issues[i]，证明该功能值得创新
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
