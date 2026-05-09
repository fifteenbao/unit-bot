"""N · 专利规避师 — PLANS 第 4 阶段（N 阶段 3 之 2）。

对应"价值设计流程 PLANS"图中的 N 块「做必要的专利规避」部分：
专利检索 / 权利要求映射 / 规避方案设计 / 律师评估清单。

⚠️ 工程意见，非法律意见。
上游依赖：n_fos
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .render import render_md as _render_md
from .schema import build_user_input
from .tools  import ALLOWED_TOOLS

STAGE       = "n_patent"
STAGE_TITLE = "N · 专利规避"

SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def render_md(product_key: str, data: dict[str, Any]) -> str:
    return _render_md(product_key, STAGE_TITLE, data)


__all__ = [
    "STAGE", "STAGE_TITLE", "SYSTEM_PROMPT", "ALLOWED_TOOLS",
    "render_md", "build_user_input",
]
