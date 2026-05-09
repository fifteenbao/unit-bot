"""N · 趋势分析师 — PLANS 第 4 阶段（N 阶段 3 之 3）。

对应"价值设计流程 PLANS"图中的 N 块「把握趋势」+「四新设计」部分：
S 曲线分析 / 系统进化趋势 / 创新方向规划 / 新材料/新工艺/新造型/新控制。

方法论：TRIZ 系统进化法则 + S 曲线。
依赖：本 agent 无前置依赖（可独立跑）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .render import render_md as _render_md
from .schema import build_user_input
from .tools  import ALLOWED_TOOLS

STAGE       = "n_trend"
STAGE_TITLE = "N · 趋势研判"

SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def render_md(product_key: str, data: dict[str, Any]) -> str:
    return _render_md(product_key, STAGE_TITLE, data)


__all__ = [
    "STAGE", "STAGE_TITLE", "SYSTEM_PROMPT", "ALLOWED_TOOLS",
    "render_md", "build_user_input",
]
