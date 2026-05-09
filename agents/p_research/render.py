"""P · 产品研究员 — JSON → markdown 渲染。"""
from __future__ import annotations

from typing import Any


def render_md(product_key: str, stage_title: str, data: dict[str, Any]) -> str:
    lines = [f"# {product_key} · {stage_title}\n"]
    if data.get("summary"):
        lines.append(f"> {data['summary']}\n")

    pos = data.get("positioning", {})
    if pos:
        lines.append("## 产品定位\n")
        lines.append(f"- **市场段**：{pos.get('target_segment', '-')}")
        lines.append(f"- **目标客群**：{pos.get('target_users', '-')}")
        lines.append(f"- **品牌矩阵角色**：{pos.get('brand_role', '-')}")
        if pos.get("key_selling_points"):
            lines.append("- **核心卖点**：")
            for p in pos["key_selling_points"]:
                lines.append(f"  - {p}")
        lines.append("")

    pains = data.get("mvp_pains", [])
    if pains:
        lines.append("## MVP 客户需求（按优先级）\n")
        lines.append("| # | 痛点 | 证据来源 |")
        lines.append("|---|------|---------|")
        for p in sorted(pains, key=lambda x: x.get("priority", 99)):
            lines.append(f"| {p.get('priority','-')} | {p.get('pain','')} | {p.get('evidence_source','')} |")
        lines.append("")

    km = data.get("key_metrics", {})
    if km:
        lines.append("## 关键指标\n")
        lines.append("| 指标 | 当前水平 |")
        lines.append("|------|---------|")
        for label, key in [
            ("吸力 (Pa)",      "suction_pa"),
            ("续航 (min)",     "battery_min"),
            ("越障 (cm)",      "obstacle_cm"),
            ("噪声 (dB)",      "noise_db"),
            ("零售价 (¥)",     "msrp_cny"),
            ("上市时间",       "release_date"),
            ("拖布配置",       "mop_config"),
        ]:
            if key in km:
                lines.append(f"| {label} | {km[key]} |")
        if km.get("dock_capabilities"):
            lines.append(f"| 基站功能 | {' / '.join(km['dock_capabilities'])} |")
        lines.append("")

    bench = data.get("benchmarks", [])
    if bench:
        lines.append("## 对标竞品\n")
        lines.append("| 对标机型 | 零售价 | 核心差异 |")
        lines.append("|---------|--------|---------|")
        for b in bench:
            lines.append(f"| {b.get('product_key','')} | ¥{b.get('msrp_cny','-')} | {b.get('key_diff','')} |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
