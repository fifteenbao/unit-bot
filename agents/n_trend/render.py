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
        ev = sc.get("industry_position_evidence", {})
        if isinstance(ev, dict) and ev:
            lines.append("- **定量证据**：")
            if ev.get("shipment_data"):    lines.append(f"  - 出货量：{ev['shipment_data']}")
            if ev.get("asp_trend"):        lines.append(f"  - 均价：{ev['asp_trend']}")
            if ev.get("spec_innovation"):  lines.append(f"  - 性能刷新：{ev['spec_innovation']}")
        if sc.get("next_s_curve_seed"):
            lines.append(f"- **下一条 S 曲线的种子**：{sc['next_s_curve_seed']}")
        lines.append("")
        sp = sc.get("subsystem_positions", [])
        if sp:
            lines.append("**子系统位置**\n")
            lines.append("| 子系统 | 位置 | 证据 | 近 3 年演进 |")
            lines.append("|--------|------|------|------------|")
            for s in sp:
                lines.append(
                    f"| {s.get('subsystem','')} | {s.get('position','')} | "
                    f"{s.get('evidence','')} | {s.get('evolution_data_3y','')} |"
                )
            lines.append("")

    ed = data.get("evolution_directions", [])
    if ed:
        lines.append("## 系统进化方向（TRIZ）\n")
        lines.append("| 趋势 | 具体路径 | 行业先行者 |")
        lines.append("|------|---------|-----------|")
        for e in ed:
            mover = e.get("first_mover", "")
            url = e.get("first_mover_url", "")
            mover_cell = f"[{mover}]({url})" if mover and url else mover
            lines.append(
                f"| {e.get('trend','')} | {e.get('concrete_pathway','')} | {mover_cell} |"
            )
        lines.append("")

    def _render_four_new_section(title: str, items: list, with_process: bool = False) -> list[str]:
        out = [f"**{title}**\n"]
        if not items:
            return out + ["_（无）_", ""]
        for x in items:
            if isinstance(x, dict):
                line = f"- {x.get('item','')}"
                if x.get("evidence_source"):
                    line += f" — 证据: {x['evidence_source']}"
                if with_process and x.get("process_id_ref"):
                    line += f" — 工艺库: `{x['process_id_ref']}`"
                out.append(line)
            else:
                out.append(f"- {x}")  # 兼容旧 list[str] 输出
        out.append("")
        return out

    fn = data.get("four_new", {})
    if fn:
        lines.append("## 四新设计机会\n")
        lines += _render_four_new_section("新材料", fn.get("new_material", []), with_process=True)
        lines += _render_four_new_section("新工艺", fn.get("new_process", []),  with_process=True)
        lines += _render_four_new_section("新造型", fn.get("new_form", []))
        lines += _render_four_new_section("新控制（智能化）", fn.get("new_control", []))

    rm = data.get("innovation_roadmap_3y", [])
    if rm:
        lines.append("## 3 年创新路线图\n")
        for r in sorted(rm, key=lambda x: x.get("year", 99)):
            dep = r.get("dependency", "")
            dep_str = f"  _依赖: {dep}_" if dep else ""
            lines.append(f"- **Year {r.get('year','?')}**: {r.get('milestone','')}{dep_str}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
