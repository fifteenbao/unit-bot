"""N · 趋势分析师 — JSON → markdown 渲染。"""
from __future__ import annotations

from typing import Any


def _bullets(items: list) -> list[str]:
    if not items:
        return ["_（无）_", ""]
    return [f"- {x}" for x in items] + [""]


def render_md(product_key: str, stage_title: str, data: dict[str, Any]) -> str:
    lines = [f"# {product_key} · {stage_title}\n"]
    if data.get("summary"):
        lines.append(f"> {data['summary']}\n")

    sc = data.get("s_curve_analysis", {})
    if sc:
        lines.append("## S 曲线分析\n")
        lines.append(f"- **行业总体位置**：{sc.get('industry_position', '-')}")
        if sc.get("next_s_curve_seed"):
            lines.append(f"- **下一条 S 曲线的种子**：{sc['next_s_curve_seed']}")
        lines.append("")
        sp = sc.get("subsystem_positions", [])
        if sp:
            lines.append("**子系统位置**\n")
            lines.append("| 子系统 | 位置 | 证据 |")
            lines.append("|--------|------|------|")
            for s in sp:
                lines.append(f"| {s.get('subsystem','')} | {s.get('position','')} | {s.get('evidence','')} |")
            lines.append("")

    ed = data.get("evolution_directions", [])
    if ed:
        lines.append("## 系统进化方向（TRIZ）\n")
        lines.append("| 趋势 | 具体路径 | 行业先行者 |")
        lines.append("|------|---------|-----------|")
        for e in ed:
            lines.append(
                f"| {e.get('trend','')} | {e.get('concrete_pathway','')} | "
                f"{e.get('first_mover','')} |"
            )
        lines.append("")

    fn = data.get("four_new", {})
    if fn:
        lines.append("## 四新设计机会\n")
        lines.append("**新材料**\n");          lines += _bullets(fn.get("new_material", []))
        lines.append("**新工艺**\n");          lines += _bullets(fn.get("new_process", []))
        lines.append("**新造型**\n");          lines += _bullets(fn.get("new_form", []))
        lines.append("**新控制（智能化）**\n");  lines += _bullets(fn.get("new_control", []))

    rm = data.get("innovation_roadmap_3y", [])
    if rm:
        lines.append("## 3 年创新路线图\n")
        for r in sorted(rm, key=lambda x: x.get("year", 99)):
            lines.append(f"- **Year {r.get('year','?')}**: {r.get('milestone','')}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
