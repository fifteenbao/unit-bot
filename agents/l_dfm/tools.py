"""L · DFM 优化师 — 工具白名单。

聚焦材料/工艺/Should Cost。重度使用 query_materials / query_suppliers。
"""
ALLOWED_TOOLS = [
    "get_product_detail",
    "get_motors",
    "get_pcb_components",
    "get_bom_cost",
    "match_bom_to_library",
    "list_components",
    "get_component",
    "query_materials",
    "query_suppliers",
    "cut_premium",
    "dfma_analysis",
    "generate_bom_estimate",     # 当前 BOM 成本基线，与 Should Cost 对比
    "find_parts",
    "web_search",
    "web_fetch",
]
