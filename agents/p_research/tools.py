"""P · 产品研究员 — 工具白名单。

只做产品定位/客户需求/对标——不读拆机数据，不算成本。
"""
ALLOWED_TOOLS = [
    "list_products",
    "get_product_detail",
    "search_by_spec",
    "compare_by_spec",
    "compare_cost_benchmark",
    "vs_compare",                # 横向对标
    "crawl_product_specs",
    "web_search",
    "web_fetch",
]
