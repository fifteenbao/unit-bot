"""P · 问题诊断师 — PLANS 第 1 阶段（P 阶段 3 之 3）。

对应"价值设计流程 PLANS"图中的 P 块「改善机会分析」部分：
- 质量问题清单 / 维修维护问题清单 / 改善机会识别
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .render import render_md as _render_md
from .schema import build_user_input
from .tools  import ALLOWED_TOOLS

STAGE       = "p_issues"
STAGE_TITLE = "P · 问题诊断"

SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def render_md(product_key: str, data: dict[str, Any]) -> str:
    return _render_md(product_key, STAGE_TITLE, data)


__all__ = [
    "STAGE", "STAGE_TITLE", "SYSTEM_PROMPT", "ALLOWED_TOOLS",
    "render_md", "build_user_input",
]
