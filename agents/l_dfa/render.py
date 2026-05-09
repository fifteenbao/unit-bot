"""L · DFA 优化师 — JSON → markdown 渲染。"""
from __future__ import annotations

from typing import Any


def render_md(product_key: str, stage_title: str, data: dict[str, Any]) -> str:
    lines = [f"# {product_key} · {stage_title}\n"]
    if data.get("summary"):
        lines.append(f"> {data['summary']}\n")

    saved_cny = data.get("total_saved_cny")
    saved_sec = data.get("total_saved_seconds")
    if saved_cny or saved_sec:
        lines.append(f"**整机降本潜力**：¥{saved_cny or 0} / 台 · 装配工时节省 {saved_sec or 0} 秒\n")

    proposals = data.get("dfa_proposals", [])
    if proposals:
        lines.append("## 9 项 DFA 优化提案\n")
        lines.append("| # | 维度 | 对象 | 现状 | 改动 | 节省(¥) | 节省(秒) | 三问 | 风险 |")
        lines.append("|---|------|------|------|------|--------|---------|------|------|")
        for p in sorted(proposals, key=lambda x: x.get("lever_id", 99)):
            lines.append(
                f"| {p.get('lever_id','-')} | {p.get('lever_name','')} | "
                f"{p.get('target_part','')} | {p.get('current_state','')} | "
                f"{p.get('proposed_change','')} | {p.get('saved_cny','')} | "
                f"{p.get('saved_seconds','')} | {p.get('boothroyd_check','')} | "
                f"{p.get('risk','')} |"
            )
        lines.append("")

    fa = data.get("fastener_audit", {})
    if fa:
        lines.append("## 紧固件审计\n")
        lines.append(f"- 螺钉数：**{fa.get('current_screw_count', '-')}** → **{fa.get('proposed_screw_count', '-')}**")
        if fa.get("current_fastener_types"):
            lines.append(f"- 当前种类：{' / '.join(fa['current_fastener_types'])}")
        if fa.get("proposed_fastener_types"):
            lines.append(f"- 建议种类：{' / '.join(fa['proposed_fastener_types'])}")
        lines.append("")

    st = data.get("standardization_targets", [])
    if st:
        lines.append("## 标准化目标\n")
        lines.append("| 类别 | 当前 SKU 数 | 建议 SKU 数 | 理由 |")
        lines.append("|------|------------|------------|------|")
        for t in st:
            lines.append(
                f"| {t.get('category','')} | {t.get('current_skus','-')} | "
                f"{t.get('proposed_skus','-')} | {t.get('rationale','')} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
