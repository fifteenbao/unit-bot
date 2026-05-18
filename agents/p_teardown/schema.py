"""P · 拆解分析师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "teardown_sequence": [
    {
      "bom_level":   int,            # 1~5，对齐工业 BOM 层级（L1 整机/基站裸机/包材 → L5 末端零件）
      "layer":       int,            # 拆解时的物理层（外壳层=1，主板层=2，子模块层=3…）
      "name":        str,
      "action":      str,
      "tool":        str,
      "difficulty":  "easy/medium/hard",
      "material":    str,            # 牌号优先（ABS181 / PC3113 / SUS304 / POM 等）
      "process":     str,            # 工艺标签（注塑/CNC/电镀/硅胶模压/PCB/SMT/线束/紧固件…）
      "mold_id":     str,            # 模号（使用你内部脱敏编号，如 MOLD-INJ-S-001），未识别填 ""
      "supply_mode": "外购/委外/自制",
      "qty":         int             # 单台用量
    }, ...
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
