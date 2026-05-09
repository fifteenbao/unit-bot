"""L · DFM 优化师 — JSON → markdown 渲染。"""
from __future__ import annotations

from typing import Any


def render_md(product_key: str, stage_title: str, data: dict[str, Any]) -> str:
    lines = [f"# {product_key} · {stage_title}\n"]
    if data.get("summary"):
        lines.append(f"> {data['summary']}\n")

    if data.get("total_saved_cny"):
        lines.append(f"**整机降本潜力**：¥{data['total_saved_cny']} / 台\n")

    proposals = data.get("dfm_proposals", [])
    if proposals:
        lines.append("## 5 项 DFM 优化提案\n")
        lines.append("| # | 维度 | 对象 | 现状 | 改动 | 节省(¥) | 工艺约束 | 风险 |")
        lines.append("|---|------|------|------|------|--------|---------|------|")
        for p in sorted(proposals, key=lambda x: x.get("lever_id", 99)):
            lines.append(
                f"| {p.get('lever_id','-')} | {p.get('lever_name','')} | "
                f"{p.get('target_part','')} | {p.get('current_spec','')} | "
                f"{p.get('proposed_spec','')} | {p.get('saved_cny','')} | "
                f"{p.get('process_constraint','')} | {p.get('risk','')} |"
            )
        lines.append("")

    sc = data.get("should_cost_analysis", [])
    if sc:
        lines.append("## 应该成本（Should Cost）建模\n")
        lines.append("| 件 | 材料 | 加工 | 利润 | 应该成本 | 当前报价 | 差距 | 谈判优先级 |")
        lines.append("|----|------|------|------|---------|---------|------|-----------|")
        for s in sc:
            lines.append(
                f"| {s.get('part','')} | ¥{s.get('material_cost','-')} | "
                f"¥{s.get('process_cost','-')} | ¥{s.get('fair_profit','-')} | "
                f"**¥{s.get('should_cost','-')}** | ¥{s.get('current_price','-')} | "
                f"¥{s.get('gap_cny','-')} | {s.get('negotiation_priority','')} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
