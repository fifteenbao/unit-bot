"""N · 趋势分析师 — 工具白名单。

工艺/模具/工具三库用于检验"新工艺"是否已进入产业供应链。
"""
ALLOWED_TOOLS = [
    "list_products",
    "get_product_detail",
    "compare_by_spec",
    "vs_compare",
    "query_materials",
    "query_processes",      # 看新工艺是否已入库 = 供应链就绪
    "query_molds",          # 看新造型对模具的影响
    "query_tooling",        # 看治具投入门槛
    "find_parts",
    "web_search",
    "web_fetch",
]
