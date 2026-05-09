"""N · 功能创新搜索师 — JSON → markdown 渲染。"""
from __future__ import annotations

from typing import Any


def render_md(product_key: str, stage_title: str, data: dict[str, Any]) -> str:
    lines = [f"# {product_key} · {stage_title}\n"]
    if data.get("summary"):
        lines.append(f"> {data['summary']}\n")

    fp = data.get("fos_proposals", [])
    if not fp:
        lines.append("_未识别可替代功能_\n")
        return "\n".join(lines).rstrip() + "\n"

    for i, p in enumerate(fp, 1):
        lines.append(f"## {i}. {p.get('original_function','')}\n")
        lines.append(f"- **抽象描述**：{p.get('abstract_description','')}")
        if p.get("cross_domain_inspiration"):
            insp = " / ".join(p["cross_domain_inspiration"]) if isinstance(p["cross_domain_inspiration"], list) else p["cross_domain_inspiration"]
            lines.append(f"- **跨领域启发**：{insp}")
        lines.append(f"- **候选替代方案**：{p.get('candidate_replacement','')}")
        if p.get("key_technologies"):
            tech = " / ".join(p["key_technologies"]) if isinstance(p["key_technologies"], list) else p["key_technologies"]
            lines.append(f"- **关键技术**：{tech}")
        if p.get("key_suppliers"):
            sup = " / ".join(p["key_suppliers"]) if isinstance(p["key_suppliers"], list) else p["key_suppliers"]
            lines.append(f"- **关键供应商**：{sup}")
        lines.append(f"- **集成难度**：{p.get('integration_difficulty','-')} | **成本对比**：{p.get('expected_cost_vs_current','-')}")
        if p.get("risks"):
            risks = " / ".join(p["risks"]) if isinstance(p["risks"], list) else p["risks"]
            lines.append(f"- **风险**：{risks}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
