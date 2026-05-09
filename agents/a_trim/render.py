"""A · 裁剪策略师 — JSON → markdown 渲染。"""
from __future__ import annotations

from typing import Any


def render_md(product_key: str, stage_title: str, data: dict[str, Any]) -> str:
    lines = [f"# {product_key} · {stage_title}\n"]
    if data.get("summary"):
        lines.append(f"> {data['summary']}\n")

    if data.get("total_saved_cny"):
        lines.append(f"**整机裁剪降本潜力**：¥{data['total_saved_cny']} / 台\n")

    td = data.get("trim_decisions", [])
    if td:
        lines.append("## 裁剪决策（三级）\n")
        lines.append("| 等级 | 对象 | 节省(¥) | 补偿方案 | 风险 | 依据 |")
        lines.append("|------|------|--------|---------|------|------|")
        for t in td:
            lines.append(
                f"| {t.get('trim_level','')} | {t.get('target','')} | "
                f"{t.get('saved_cny','-')} | {t.get('compensation','')} | "
                f"{t.get('risk_assessment','')} | {t.get('evidence_from_function_model','')} |"
            )
        lines.append("")

    tc = data.get("technical_contradictions", [])
    if tc:
        lines.append("## 技术矛盾（TRIZ 矛盾矩阵）\n")
        for c in tc:
            principles = " / ".join(c.get("candidate_principles", [])) if isinstance(c.get("candidate_principles"), list) else ""
            lines.append(f"- **{c.get('param_to_improve','')} ↑ → {c.get('param_that_worsens','')} ↑**")
            if principles:
                lines.append(f"  - 候选发明原理：{principles}")
            lines.append(f"  - 具体方案：{c.get('concrete_proposal','')}")
        lines.append("")

    pc = data.get("physical_contradictions", [])
    if pc:
        lines.append("## 物理矛盾（分离方法）\n")
        for c in pc:
            demands = " / ".join(c.get("opposite_demands", [])) if isinstance(c.get("opposite_demands"), list) else ""
            lines.append(f"- **{c.get('param','')}**：同时要求 {demands}")
            lines.append(f"  - 分离方法：**{c.get('separation_method','')}**")
            lines.append(f"  - 具体方案：{c.get('concrete_proposal','')}")
        lines.append("")

    ab = data.get("architectural_bottlenecks", [])
    if ab:
        lines.append("## 架构瓶颈（N 阶段输入）\n")
        for b in ab:
            mark = "🔴 需进入 N 阶段" if b.get("needs_n_stage") else "🟡 持续观察"
            lines.append(f"- {b.get('description','')} — {mark}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
