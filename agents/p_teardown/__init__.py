"""P · 拆解分析师 — PLANS 第 1 阶段（P 阶段 3 之 2）。

对应"价值设计流程 PLANS"图中的 P 块「拆解与装配分析」部分：
- 产品拆解流程 / 装配流程逆向 / 最少件清单 / 装配问题清单
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .render import render_md as _render_md
from .schema import build_user_input
from .tools  import ALLOWED_TOOLS

STAGE       = "p_teardown"
STAGE_TITLE = "P · 拆解分析"

SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def render_md(product_key: str, data: dict[str, Any]) -> str:
    return _render_md(product_key, STAGE_TITLE, data)


__all__ = [
    "STAGE", "STAGE_TITLE", "SYSTEM_PROMPT", "ALLOWED_TOOLS",
    "render_md", "build_user_input",
]
