"""S · 平台架构师 — 工具白名单。

从产品矩阵视角看复杂度 + 共件率 + 共模率 + 工艺标准化度。
"""
ALLOWED_TOOLS = [
    "list_products",
    "get_product_detail",
    "compare_cost_benchmark",
    "find_parts",
    "list_components",
    "match_bom_to_library",
    "query_processes",       # 看跨机型工艺标准化度
    "query_molds",           # 拿现有共模数据 (mold_reuse_count + ROI 量化)
    "query_tooling",         # 看治具/夹具复用度
    "query_suppliers",
    "web_search",
]
