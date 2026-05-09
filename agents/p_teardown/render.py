"""P · 拆解分析师 — JSON → markdown 渲染。"""
from __future__ import annotations

from typing import Any


def render_md(product_key: str, stage_title: str, data: dict[str, Any]) -> str:
    lines = [f"# {product_key} · {stage_title}\n"]
    if data.get("summary"):
        lines.append(f"> {data['summary']}\n")

    seq = data.get("teardown_sequence", [])
    if seq:
        lines.append("## 拆解流程\n")
        lines.append("| 层 | 部件 | 动作 | 工具 | 难度 |")
        lines.append("|---|------|------|------|------|")
        for s in seq:
            lines.append(
                f"| {s.get('layer','-')} | {s.get('name','')} | {s.get('action','')} | "
                f"{s.get('tool','')} | {s.get('difficulty','')} |"
            )
        lines.append("")

    inf = data.get("assembly_inference", {})
    if inf:
        lines.append("## 装配流程逆向分析\n")
        lines.append(f"- **装配方向**：{inf.get('order_pattern', '-')}")
        lines.append(f"- **紧固件总数**：{inf.get('fastener_count', '-')}")
        if inf.get("fastener_types"):
            lines.append(f"- **紧固件种类**：{' / '.join(inf['fastener_types'])}")
        lines.append(f"- **估算装配工时**：{inf.get('estimated_assembly_seconds', '-')} 秒")
        lines.append("")

    mc = data.get("min_parts_candidates", [])
    if mc:
        lines.append("## 最少件候选（DFA 三问法）\n")
        lines.append("| 当前件 | 当前角色 | 合并目标 | 三问判定 |")
        lines.append("|-------|---------|---------|---------|")
        for c in mc:
            lines.append(
                f"| {c.get('part','')} | {c.get('current_role','')} | "
                f"{c.get('merge_target','')} | {c.get('rationale','')} |"
            )
        lines.append("")

    pp = data.get("assembly_pain_points", [])
    if pp:
        lines.append("## 装配反模式问题\n")
        lines.append("| 类型 | 位置 | 证据 |")
        lines.append("|------|------|------|")
        for p in pp:
            lines.append(f"| {p.get('issue','')} | {p.get('location','')} | {p.get('evidence','')} |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
