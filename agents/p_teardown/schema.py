"""P · 拆解分析师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "teardown_sequence": [
    {"layer": int, "name": str, "action": str, "tool": str, "difficulty": "easy/medium/hard"}, ...
  ],
  "assembly_inference": {
    "order_pattern":             "自上而下/多向/翻转",
    "fastener_count":            int,
    "fastener_types":            [str, ...],
    "estimated_assembly_seconds": int
  },
  "min_parts_candidates": [
    {"part": str, "current_role": str, "merge_target": str, "rationale": str}, ...
  ],
  "assembly_pain_points": [
    {"issue": str, "location": str, "evidence": str}, ...
  ],
  "summary": str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型：{product_key}\n\n"
        "请按 P 阶段【拆解分析师】职责，还原拆解流程、推断装配顺序、"
        "用 DFA 三问法识别可合并件、列出装配反模式问题。"
        "完成后只输出一段 ```json 代码块。"
    )
