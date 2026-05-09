"""S · 成本体系构建师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "organization": {
    "key_roles":         [{"role": str, "responsibilities": str, "headcount": int}, ...],
    "review_committees": [str, ...],
    "meeting_cadence":   str,
    "kpis":              [str, ...]
  },
  "facility": {
    "teardown_lab":   [str, ...],
    "data_platforms": [str, ...],
    "modeling_tools": [str, ...],
    "dashboards":     [str, ...]
  },
  "capability": {
    "training_paths":   [str, ...],
    "certifications":   [str, ...],
    "knowledge_assets": [str, ...]
  },
  "data": {
    "update_cadence":    [{"db": str, "frequency": str}, ...],
    "ownership":         [{"db": str, "owner_role": str}, ...],
    "confidence_tiers":  [str, ...],
    "sharing_mechanism": str
  },
  "process": {
    "npi_gates": [
      {"gate": int, "name": str, "plans_requirement": str}, ...
    ]
  },
  "summary": str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型（作为切入视角，但要看整个组织）：{product_key}\n\n"
        "请按 S 阶段【成本体系构建师】职责，给出组织/设施/能力/数据/流程 5 维体系建设方案。"
        "完成后只输出一段 ```json 代码块。"
    )
