"""S · 平台架构师 — JSON → markdown 渲染。"""
from __future__ import annotations

from typing import Any


def render_md(product_key: str, stage_title: str, data: dict[str, Any]) -> str:
    lines = [f"# {product_key} · {stage_title}\n"]
    if data.get("summary"):
        lines.append(f"> {data['summary']}\n")

    ca = data.get("complexity_assessment", {})
    if ca:
        lines.append("## 产品复杂性评估\n")
        lines.append(f"- **SKU 数**：{ca.get('sku_count', '-')}")
        lines.append(f"- **共件率**：{ca.get('shared_parts_rate', '-')}")
        lines.append(f"- **平台化程度**：{ca.get('platformization_score', '-')}")
        lines.append(f"- **复杂度评分**：**{ca.get('complexity_score', '-')}** / 1.0")
        if ca.get("complexity_evidence"):
            lines.append(f"- **证据**：{ca['complexity_evidence']}")
        lines.append("")

    pc = data.get("platform_candidates", [])
    if pc:
        lines.append("## 平台化候选子系统\n")
        lines.append("| 子系统 | 频次 | 跨机型差异 | ROI 优先级 | 理由 |")
        lines.append("|--------|------|-----------|-----------|------|")
        for p in pc:
            lines.append(
                f"| {p.get('subsystem','')} | {p.get('frequency','')} | "
                f"{p.get('cross_model_variance','')} | {p.get('roi_priority','')} | "
                f"{p.get('rationale','')} |"
            )
        lines.append("")

    pd = data.get("platform_designs", [])
    if pd:
        lines.append("## 具体平台设计\n")
        for p in pd:
            covers = " / ".join(p["covers_models"]) if isinstance(p.get("covers_models"), list) else p.get("covers_models", "")
            params = " / ".join(p["variable_params"]) if isinstance(p.get("variable_params"), list) else p.get("variable_params", "")
            stds = " / ".join(p["interface_standards"]) if isinstance(p.get("interface_standards"), list) else p.get("interface_standards", "")
            lines.append(f"### {p.get('platform_name', '')}")
            lines.append(f"- **覆盖机型**：{covers}")
            lines.append(f"- **可变参数**：{params}")
            lines.append(f"- **接口标准**：{stds}")
            lines.append(f"- **预期 ROI**：{p.get('expected_roi', '')}")
            lines.append("")

    cp = data.get("complexity_process", [])
    if cp:
        lines.append("## 复杂性管理流程\n")
        for step in cp:
            lines.append(f"- {step}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
