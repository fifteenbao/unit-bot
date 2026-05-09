"""P · 产品研究员 — PLANS 第 1 阶段（P 阶段 3 之 1）。

对应"价值设计流程 PLANS"图中的 P 块「产品定位研究」部分：
- 产品定位分析 / 客户需求分析（MVP）/ 关键指标分析 / 对标分析
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .render import render_md as _render_md
from .schema import build_user_input
from .tools  import ALLOWED_TOOLS

STAGE       = "p_research"
STAGE_TITLE = "P · 产品研究"

SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def render_md(product_key: str, data: dict[str, Any]) -> str:
    return _render_md(product_key, STAGE_TITLE, data)


__all__ = [
    "STAGE", "STAGE_TITLE", "SYSTEM_PROMPT", "ALLOWED_TOOLS",
    "render_md", "build_user_input",
]
