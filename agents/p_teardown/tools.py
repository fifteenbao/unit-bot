"""P · 拆解分析师 — 工具白名单。

读拆机数据库 + FCC OCR 结果 → 还原拆解/装配流程。
当拆机数据不全时，主动生成拆机 CSV；成本分类和估算必须使用项目配置或对应行业案例。扫地机器人项目可使用 7 桶框架，其他行业不得套用。
"""
ALLOWED_TOOLS = [
    "get_product_detail",
    "get_motors",
    "get_sensors",
    "get_pcb_components",
    "get_missing_data",
    "match_bom_to_library",
    "find_parts",
    # 主动生成拆机数据（取代旧 /bom 命令）
    "generate_teardown_csv",
    "generate_bom_estimate",
    "get_bom_cost",
    "web_search",
    "web_fetch",
]
