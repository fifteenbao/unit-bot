"""L · DFA 优化师 — 工具白名单。

主要看件清单 + 标准件库匹配 + DFMA 象限 + 装配工时基线。不读材料库（那是 DFM 的活）。
"""
ALLOWED_TOOLS = [
    "get_product_detail",
    "get_motors",
    "get_pcb_components",
    "get_bom_cost",
    "match_bom_to_library",
    "list_components",
    "get_component",
    "find_parts",
    "dfma_analysis",
    "query_processes",       # 装配工时基线（P_FAST_SCREW / SNAP / BOND / WELD_SOLDER）
    "web_search",
]
