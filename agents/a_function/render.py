"""A · 功能建模师 — JSON → markdown 渲染。"""
from __future__ import annotations

from typing import Any


def render_md(product_key: str, stage_title: str, data: dict[str, Any]) -> str:
    lines = [f"# {product_key} · {stage_title}\n"]
    if data.get("summary"):
        lines.append(f"> {data['summary']}\n")

    fm = data.get("function_model", [])
    if fm:
        lines.append("## 功能-载体模型\n")
        lines.append("| 功能 | 类型 | 载体 | 价值 | 成本占比 | V/C |")
        lines.append("|------|------|------|------|---------|-----|")
        for f in fm:
            carriers = " / ".join(f.get("carriers", [])) if isinstance(f.get("carriers"), list) else f.get("carriers", "")
            lines.append(
                f"| {f.get('function','')} | {f.get('function_type','')} | "
                f"{carriers} | {f.get('value_score','-')} | {f.get('cost_share','-')} | "
                f"**{f.get('v_over_c','-')}** |"
            )
        lines.append("")

    od = data.get("over_design", [])
    if od:
        lines.append("## 过设计（V/C < 0.8）\n")
        lines.append("| 功能 | 载体 | V/C | 证据 |")
        lines.append("|------|------|-----|------|")
        for o in od:
            lines.append(f"| {o.get('function','')} | {o.get('carrier','')} | {o.get('v_over_c','-')} | {o.get('evidence','')} |")
        lines.append("")

    ud = data.get("under_design", [])
    if ud:
        lines.append("## 欠设计（V/C > 1.2）\n")
        lines.append("| 功能 | 用户痛点 | 证据 |")
        lines.append("|------|---------|------|")
        for u in ud:
            lines.append(f"| {u.get('function','')} | {u.get('user_pain','')} | {u.get('evidence','')} |")
        lines.append("")

    fr = data.get("function_redundancy", [])
    if fr:
        lines.append("## 功能冗余（多载体实现同一功能）\n")
        for r in fr:
            carriers = " / ".join(r.get("carriers", [])) if isinstance(r.get("carriers"), list) else r.get("carriers", "")
            lines.append(f"- **{r.get('function','')}**：{carriers} — {r.get('rationale','')}")
        lines.append("")

    fg = data.get("function_gaps", [])
    if fg:
        lines.append("## 功能缺失（用户期待但未实现）\n")
        for g in fg:
            lines.append(f"- **{g.get('missing_function','')}**：{g.get('user_expectation','')}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
