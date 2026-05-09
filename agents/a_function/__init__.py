"""A · 功能建模师 — PLANS 第 3 阶段（A 阶段 2 之 1）。

对应"价值设计流程 PLANS"图中的 A 块「功能分析（逆向）」部分：
功能建模 / 功能价值分析 / 功能缺陷识别。

方法论：TRIZ 功能分析。
上游依赖：l_dfa + l_dfm
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .render import render_md as _render_md
from .schema import build_user_input
from .tools  import ALLOWED_TOOLS

STAGE       = "a_function"
STAGE_TITLE = "A · 功能建模"

SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def render_md(product_key: str, data: dict[str, Any]) -> str:
    return _render_md(product_key, STAGE_TITLE, data)


__all__ = [
    "STAGE", "STAGE_TITLE", "SYSTEM_PROMPT", "ALLOWED_TOOLS",
    "render_md", "build_user_input",
]
