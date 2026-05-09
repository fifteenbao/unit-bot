"""N · 功能创新搜索师 — PLANS 第 4 阶段（N 阶段 3 之 1）。

对应"价值设计流程 PLANS"图中的 N 块「功能创新」部分：
- 跨领域搜索和筛选功能替代方案 (FOS — Function-Oriented Search)
- 落实功能实现新方案

方法论：FOS 跨领域功能搜索。
上游依赖：a_trim
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .render import render_md as _render_md
from .schema import build_user_input
from .tools  import ALLOWED_TOOLS

STAGE       = "n_fos"
STAGE_TITLE = "N · 跨领域功能搜索"

SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def render_md(product_key: str, data: dict[str, Any]) -> str:
    return _render_md(product_key, STAGE_TITLE, data)


__all__ = [
    "STAGE", "STAGE_TITLE", "SYSTEM_PROMPT", "ALLOWED_TOOLS",
    "render_md", "build_user_input",
]
