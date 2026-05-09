"""L · DFA 优化师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "dfa_proposals": [
    {
      "lever_id": int,                   # 1..9 对应 9 项优化方向
      "lever_name": str,
      "target_part": str,
      "current_state": str,
      "proposed_change": str,
      "saved_cny": int,
      "saved_seconds": int,
      "risk": str,
      "boothroyd_check": str             # 三问法判定
    }, ...
  ],
  "fastener_audit": {
    "current_screw_count":      int,
    "proposed_screw_count":     int,
    "current_fastener_types":   [str, ...],
    "proposed_fastener_types":  [str, ...]
  },
  "standardization_targets": [
    {"category": str, "current_skus": int, "proposed_skus": int, "rationale": str}, ...
  ],
  "total_saved_cny":     int,
  "total_saved_seconds": int,
  "summary": str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型：{product_key}\n\n"
        "请按 L 阶段【DFA 优化师】职责，给出 9 项优化方向的可执行清单 + "
        "紧固件审计 + 标准化建议。完成后只输出一段 ```json 代码块。"
    )
