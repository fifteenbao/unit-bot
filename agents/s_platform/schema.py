"""S · 平台架构师 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "complexity_assessment": {
    "sku_count":              int,           # list_products 取真实数
    "shared_parts_count":     int,           # find_parts 跨机型共用件数
    "total_parts_count":      int,           # 整机型件总数 (含独有件)
    "shared_parts_rate":      float,         # = shared_parts_count / total_parts_count
    "mold_reuse_count":       int,           # query_molds 中 related_parts >= 2 的模号数 (实测共模数)
    "platformization_score":  float,         # 0~1
    "complexity_score":       float,         # 0~1, 越高越复杂
    "complexity_evidence":    str            # 必填: 引用具体 list_products + find_parts 结果
  },
  "platform_candidates": [
    {
      "subsystem":            str,
      "rationale":            str,
      "frequency":            "高/中/低",
      "cross_model_variance": "高/中/低",
      "current_mold_ids":     [str, ...],    # 该子系统当前用到的模号 (来自 query_molds)
      "evidence_from_trim":   str,           # 引用 trim.architectural_bottlenecks[i] 或 trim_decisions[i]
      "evidence_from_fos":    str,           # 引用 fos.fos_proposals[i] (如有)
      "roi_priority":         "高/中/低"
    }, ...
  ],
  "platform_designs": [
    {
      "platform_name":         str,            # XX-Platform-vY
      "covers_models":         [str, ...],
      "variable_params":       [str, ...],
      "interface_standards":   [str, ...],
      "mold_strategy":         str,            # 共模 1+1 / 2+2 / 模块化插拔 等
      "roi_should_cost_delta": str,            # 量化 ROI：用 query_processes/molds 算 unit_amortization 减少幅度
      "expected_roi":          str             # 文字总结 (开发周期、采购规模、维修便利)
    }, ...
  ],
  "complexity_process":      [str, ...],       # 立项守门 / KPI / 退役机制等流程建议
  "summary":                 str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型（作为切入视角，但要看整个产品矩阵）：{product_key}\n\n"
        "请按 S 阶段【平台架构师】职责，做产品复杂性评分、平台化候选识别、"
        "具体平台设计、复杂性管理流程建议。完成后只输出一段 ```json 代码块。"
    )
