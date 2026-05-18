"""L · DFM 优化师 — 工具白名单。

聚焦材料/工艺/模具/工具/Should Cost。
五要素查库：query_materials + query_processes + query_molds + query_tooling + query_suppliers。
"""
ALLOWED_TOOLS = [
    "get_product_detail",
    "get_motors",
    "get_pcb_components",
    "get_bom_cost",
    "match_bom_to_library",
    "list_components",
    "get_component",
    # Should Cost 五要素查库
    "query_materials",
    "query_processes",           # processes.csv: 22 条工艺基线
    "query_molds",               # molds.csv: 25 条模号摊销
    "query_tooling",             # tooling.csv: 21 条夹具/刀具折旧
    "query_suppliers",
    "cut_premium",
    "dfma_analysis",
    "generate_bom_estimate",     # 当前 BOM 成本基线，与 Should Cost 对比
    "find_parts",
    "web_search",
    "web_fetch",
]
