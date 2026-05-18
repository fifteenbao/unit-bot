"""P · 问题诊断师 — JSON → markdown 渲染。"""
from __future__ import annotations

from typing import Any


def render_md(product_key: str, stage_title: str, data: dict[str, Any]) -> str:
    lines = [f"# {product_key} · {stage_title}\n"]
    if data.get("summary"):
        lines.append(f"> {data['summary']}\n")

    qi = data.get("quality_issues", [])
    if qi:
        lines.append("## 质量问题清单\n")
        lines.append("| 现象 | 频次 | 频次% | 关键件 | 影响 | 来源 |")
        lines.append("|------|------|------|-------|------|------|")
        for q in qi:
            pct = q.get("frequency_pct", -1)
            pct_str = f"{pct:.1f}%" if isinstance(pct, (int, float)) and pct >= 0 else "—"
            kp = "✓ " + q.get("key_part_name", "") if q.get("key_part_flag") else ""
            src = q.get("evidence_source", "")
            url = q.get("evidence_url", "")
            src_cell = f"[{src}]({url})" if url else src
            lines.append(
                f"| {q.get('phenomenon','')} | {q.get('frequency','')} | {pct_str} | "
                f"{kp} | {q.get('impact','')} | {src_cell} |"
            )
        lines.append("")

    si = data.get("service_issues", [])
    if si:
        lines.append("## 维修维护问题\n")
        lines.append("| 范畴 | 问题 | 用户影响 |")
        lines.append("|------|------|---------|")
        for s in si:
            lines.append(
                f"| {s.get('area','')} | {s.get('issue','')} | {s.get('user_impact','')} |"
            )
        lines.append("")

    io = data.get("improvement_opportunities", [])
    if io:
        lines.append("## 改善机会方向\n")
        lines.append("| 改善机会 | 归类 |")
        lines.append("|---------|------|")
        for o in io:
            lines.append(f"| {o.get('opportunity','')} | {o.get('category','')} |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
