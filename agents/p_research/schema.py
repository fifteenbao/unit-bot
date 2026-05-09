"""P · 产品研究员 — 输入构造 + 输出 schema 文档。"""

OUTPUT_SCHEMA_DOC = """
{
  "positioning": {
    "target_segment":     "旗舰/中高端/入门",
    "target_users":       str,
    "brand_role":         "旗舰/走量/价格屠夫/实验",
    "key_selling_points": [str, ...]
  },
  "mvp_pains": [
    {"pain": str, "evidence_source": str, "priority": int}, ...
  ],
  "key_metrics": {
    "suction_pa":        int,
    "battery_min":       int,
    "obstacle_cm":       float,
    "noise_db":          int,
    "msrp_cny":          int,
    "release_date":      "YYYY-MM",
    "mop_config":        str,
    "dock_capabilities": [str, ...]
  },
  "benchmarks": [
    {"product_key": str, "msrp_cny": int, "key_diff": str}, ...
  ],
  "summary": str
}
"""


def build_user_input(product_key: str) -> str:
    return (
        f"目标机型：{product_key}\n\n"
        "请按 P 阶段【产品研究员】职责，调研产品定位、MVP 客户需求、"
        "关键指标、对标竞品。完成后只输出一段 ```json 代码块。"
    )
