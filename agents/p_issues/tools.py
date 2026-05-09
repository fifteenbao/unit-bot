"""P · 问题诊断师 — 工具白名单。

重度依赖 web_search 找用户评论/维修视频/故障案例。
"""
ALLOWED_TOOLS = [
    "get_product_detail",
    "compare_by_spec",
    "web_search",
    "web_fetch",
]
