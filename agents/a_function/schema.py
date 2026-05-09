"""A · 功能建模师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "function_model": [
    {
      "function":      str,
      "function_type": "MF/AF/AdditionalF/HarmfulF",
      "carriers":      [str, ...],
      "value_score":   float,    # 0~1.5
      "cost_share":    float,    # 0~1
      "v_over_c":      float
    }, ...
  ],
  "over_design": [
    {"function": str, "carrier": str, "v_over_c": float, "evidence": str}, ...
  ],
  "under_design": [
    {"function": str, "user_pain": str, "evidence": str}, ...
  ],
  "function_redundancy": [
    {"function": str, "carriers": [str, ...], "rationale": str}, ...
  ],
  "function_gaps": [
    {"missing_function": str, "user_expectation": str}, ...
  ],
  "summary": str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型：{product_key}\n\n"
        "请按 A 阶段【功能建模师】职责，建「功能-载体」模型 + 价值/成本比分析 + "
        "识别过设计/欠设计/冗余/缺失。完成后只输出一段 ```json 代码块。"
    )
