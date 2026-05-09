"""N · 专利规避师 — JSON → markdown 渲染。"""
from __future__ import annotations

from typing import Any


def render_md(product_key: str, stage_title: str, data: dict[str, Any]) -> str:
    lines = [f"# {product_key} · {stage_title}\n"]
    lines.append("> ⚠️ 工程意见，非法律意见。最终是否构成侵权由专业 IP 律师评估。\n")
    if data.get("summary"):
        lines.append(f"> {data['summary']}\n")

    pl = data.get("patent_landscape", [])
    if pl:
        lines.append("## 专利布局总览\n")
        lines.append("| 玩家 | 密度 | 关键布局领域 |")
        lines.append("|------|------|-------------|")
        for p in pl:
            areas = " / ".join(p["key_patent_areas"]) if isinstance(p.get("key_patent_areas"), list) else p.get("key_patent_areas", "")
            lines.append(f"| {p.get('key_player','')} | {p.get('patent_density','')} | {areas} |")
        lines.append("")

    rp = data.get("risk_patents", [])
    if rp:
        lines.append("## 风险专利清单\n")
        lines.append("| 专利号 | 标题 | 与候选方案的关系 | 风险等级 |")
        lines.append("|--------|------|----------------|---------|")
        for r in rp:
            lines.append(
                f"| {r.get('patent_id','')} | {r.get('title','')} | "
                f"{r.get('match_to_candidate','')} | {r.get('risk_level','')} |"
            )
        lines.append("")
        # 详细 claims
        lines.append("### 关键权利要求详情\n")
        for r in rp:
            claims = r.get("key_claims", [])
            if claims:
                lines.append(f"**{r.get('patent_id','')}** — {r.get('title','')}")
                for c in claims:
                    lines.append(f"  - {c}")
                lines.append("")

    da = data.get("design_around_options", [])
    if da:
        lines.append("## 规避方案选项\n")
        lines.append("| 策略 | 具体改动 | 损失能力 | 工程成本 | 残留风险 |")
        lines.append("|------|---------|---------|---------|---------|")
        for d in da:
            lines.append(
                f"| {d.get('strategy','')} | {d.get('concrete_change','')} | "
                f"{d.get('lost_capability','')} | {d.get('engineering_cost','')} | "
                f"{d.get('residual_risk','')} |"
            )
        lines.append("")

    nr = data.get("needs_lawyer_review", [])
    if nr:
        lines.append("## 需律师专项评估\n")
        for n in nr:
            lines.append(f"- **{n.get('item','')}** — {n.get('reason','')}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
