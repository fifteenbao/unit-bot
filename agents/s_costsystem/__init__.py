"""S · 成本体系构建师 — PLANS 第 5 阶段（S 阶段 2 之 2）。

对应"价值设计流程 PLANS"图中的 S 块「成本体系建设」5 维：
组织建设 / 设施建设 / 能力建设 / 数据建设 / 流程建设（PLANS → NPI）。

上游依赖：a_trim + n_fos
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .render import render_md as _render_md
from .schema import build_user_input
from .tools  import ALLOWED_TOOLS

STAGE       = "s_costsystem"
STAGE_TITLE = "S · 成本体系"

SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def render_md(product_key: str, data: dict[str, Any]) -> str:
    return _render_md(product_key, STAGE_TITLE, data)


__all__ = [
    "STAGE", "STAGE_TITLE", "SYSTEM_PROMPT", "ALLOWED_TOOLS",
    "render_md", "build_user_input",
]
