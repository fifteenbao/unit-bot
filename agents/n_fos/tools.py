"""N · 功能创新搜索师 — 工具白名单。

跨领域 FOS：web_search 是绝对核心；新工艺/模具可行性查 processes/molds/tooling 三库。
"""
ALLOWED_TOOLS = [
    "get_product_detail",
    "get_motors",
    "get_pcb_components",
    "vs_compare",
    "compare_by_spec",
    "query_materials",
    "query_processes",       # 验证新工艺可行性 (3D 打印/共模/激光焊 等)
    "query_molds",           # 看是否能复用现成模具或共模
    "query_tooling",         # 看治具是否需要重新投入
    "query_suppliers",
    "find_parts",
    "web_search",
    "web_fetch",
]
