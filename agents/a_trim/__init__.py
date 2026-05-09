"""A · 裁剪策略师 — PLANS 第 3 阶段（A 阶段 2 之 2）。

对应"价值设计流程 PLANS"图中的 A 块「裁剪策略」+「矛盾解决（TRIZ）」：
三级裁剪 + 技术矛盾矩阵 + 物理矛盾分离 + 架构瓶颈识别。

方法论：TRIZ 裁剪 + 矛盾矩阵 + 4 种分离方法。
上游依赖：a_function
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .render import render_md as _render_md
from .schema import build_user_input
from .tools  import ALLOWED_TOOLS

STAGE       = "a_trim"
STAGE_TITLE = "A · 裁剪策略"

SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def render_md(product_key: str, data: dict[str, Any]) -> str:
    return _render_md(product_key, STAGE_TITLE, data)


__all__ = [
    "STAGE", "STAGE_TITLE", "SYSTEM_PROMPT", "ALLOWED_TOOLS",
    "render_md", "build_user_input",
]
