"""L · DFM 优化师 — PLANS 第 2 阶段（L 阶段 2 之 2）。

对应"价值设计流程 PLANS"图中的 L 块「DFM 优化」+「采购降本（Should Cost）」：
材料替代 / 工艺改变 / 加工精度 / 表面处理 / 结构简化 + 应该成本谈判。

上游依赖：p_teardown
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .render import render_md as _render_md
from .schema import build_user_input
from .tools  import ALLOWED_TOOLS

STAGE       = "l_dfm"
STAGE_TITLE = "L · DFM 优化"

SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def render_md(product_key: str, data: dict[str, Any]) -> str:
    return _render_md(product_key, STAGE_TITLE, data)


__all__ = [
    "STAGE", "STAGE_TITLE", "SYSTEM_PROMPT", "ALLOWED_TOOLS",
    "render_md", "build_user_input",
]
