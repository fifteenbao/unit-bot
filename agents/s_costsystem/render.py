"""S · 成本体系构建师 — JSON → markdown 渲染。"""
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

    org = data.get("organization", {})
    if org:
        lines.append("## 组织建设\n")
        roles = org.get("key_roles", [])
        if roles:
            lines.append("**关键岗位**\n")
            lines.append("| 岗位 | 职责 | 编制 |")
            lines.append("|------|------|------|")
            for r in roles:
                lines.append(f"| {r.get('role','')} | {r.get('responsibilities','')} | {r.get('headcount','-')} |")
            lines.append("")
        if org.get("review_committees"):
            lines.append("**评审组织**\n");  lines += _bullets(org["review_committees"])
        if org.get("meeting_cadence"):
            lines.append(f"**会议机制**：{org['meeting_cadence']}\n")
        if org.get("kpis"):
            lines.append("**KPI**\n");       lines += _bullets(org["kpis"])

    fac = data.get("facility", {})
    if fac:
        lines.append("## 设施建设\n")
        for label, key in [
            ("拆解实验室",   "teardown_lab"),
            ("数据平台",     "data_platforms"),
            ("建模工具",     "modeling_tools"),
            ("看板报表",     "dashboards"),
        ]:
            if fac.get(key):
                lines.append(f"**{label}**\n");  lines += _bullets(fac[key])

    cap = data.get("capability", {})
    if cap:
        lines.append("## 能力建设\n")
        for label, key in [
            ("培训路线",     "training_paths"),
            ("认证机制",     "certifications"),
            ("知识资产",     "knowledge_assets"),
        ]:
            if cap.get(key):
                lines.append(f"**{label}**\n"); lines += _bullets(cap[key])

    dat = data.get("data", {})
    if dat:
        lines.append("## 数据建设\n")
        if dat.get("update_cadence"):
            lines.append("**更新频率**\n")
            lines.append("| 数据库 | 频率 |")
            lines.append("|--------|------|")
            for u in dat["update_cadence"]:
                lines.append(f"| {u.get('db','')} | {u.get('frequency','')} |")
            lines.append("")
        if dat.get("ownership"):
            lines.append("**责任人**\n")
            lines.append("| 数据库 | 责任岗位 |")
            lines.append("|--------|---------|")
            for o in dat["ownership"]:
                lines.append(f"| {o.get('db','')} | {o.get('owner_role','')} |")
            lines.append("")
        if dat.get("confidence_tiers"):
            lines.append("**可信度等级**\n");   lines += _bullets(dat["confidence_tiers"])
        if dat.get("sharing_mechanism"):
            lines.append(f"**共享机制**：{dat['sharing_mechanism']}\n")

    proc = data.get("process", {})
    gates = proc.get("npi_gates", []) if proc else []
    if gates:
        lines.append("## 流程建设（PLANS 嵌入 NPI Gates）\n")
        lines.append("| Gate | 名称 | PLANS 要求 |")
        lines.append("|------|------|-----------|")
        for g in sorted(gates, key=lambda x: x.get("gate", 99)):
            lines.append(f"| {g.get('gate','-')} | {g.get('name','')} | {g.get('plans_requirement','')} |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
