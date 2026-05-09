"""S · 平台架构师 — PLANS 第 5 阶段（S 阶段 2 之 1）。

对应"价值设计流程 PLANS"图中的 S 块「复杂性管理」部分：
产品复杂性分析 / 平台化模块化设计 / 复杂性管理流程。

上游依赖：a_trim + n_fos
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .render import render_md as _render_md
from .schema import build_user_input
from .tools  import ALLOWED_TOOLS

STAGE       = "s_platform"
STAGE_TITLE = "S · 平台架构"

SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def render_md(product_key: str, data: dict[str, Any]) -> str:
    return _render_md(product_key, STAGE_TITLE, data)


__all__ = [
    "STAGE", "STAGE_TITLE", "SYSTEM_PROMPT", "ALLOWED_TOOLS",
    "render_md", "build_user_input",
]
