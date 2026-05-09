"""PLANS 研究库 — 第 6 个数据库。

负责 data/plans/plans_db.json 的读写和 data/plans/{slug}/{stage}.md 报告生成。
PLANS = P 现状研究 / L 精益设计 / A 先进裁剪 / N 价值创新 / S 体系建设。

stages 字段命名采用全称：p_research / l_lean / a_trim / n_innovate / s_system。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

PLANS_DIR = Path(__file__).resolve().parent.parent / "data" / "plans"
PLANS_DB  = PLANS_DIR / "plans_db.json"

STAGES = (
    # P 阶段 — 现状研究（3 agent）
    "p_research", "p_teardown", "p_issues",
    # L 阶段 — 精益设计（2 agent）
    "l_dfa", "l_dfm",
    # A 阶段 — 先进裁剪 / TRIZ（2 agent）
    "a_function", "a_trim",
    # N 阶段 — 价值创新（3 agent）
    "n_fos", "n_patent", "n_trend",
    # S 阶段 — 体系建设（2 agent）
    "s_platform", "s_costsystem",
)

STAGE_TITLES = {
    "p_research":   "P · 产品研究",
    "p_teardown":   "P · 拆解分析",
    "p_issues":     "P · 问题诊断",
    "l_dfa":        "L · DFA 优化",
    "l_dfm":        "L · DFM 优化",
    "a_function":   "A · 功能建模",
    "a_trim":       "A · 裁剪策略",
    "n_fos":        "N · 跨领域功能搜索",
    "n_patent":     "N · 专利规避",
    "n_trend":      "N · 趋势研判",
    "s_platform":   "S · 平台架构",
    "s_costsystem": "S · 成本体系",
}

# 阶段属于哪个 PLANS 大阶段（用于 UI 分组、引导文案）
STAGE_PHASE = {
    "p_research": "P", "p_teardown": "P", "p_issues": "P",
    "l_dfa": "L", "l_dfm": "L",
    "a_function": "A", "a_trim": "A",
    "n_fos": "N", "n_patent": "N", "n_trend": "N",
    "s_platform": "S", "s_costsystem": "S",
}

# 依赖关系（来自 价值设计流程PLANS.md 第 528 行数据流图）
STAGE_DEPS: dict[str, tuple[str, ...]] = {
    # P 阶段：3 个 agent 都独立可跑
    "p_research":   (),
    "p_teardown":   (),
    "p_issues":     (),
    # L 阶段：依赖 P 阶段拆解和问题清单
    "l_dfa":        ("p_teardown", "p_issues"),
    "l_dfm":        ("p_teardown",),
    # A 阶段：依赖 L 阶段输出
    "a_function":   ("l_dfa", "l_dfm"),
    "a_trim":       ("a_function",),
    # N 阶段：FOS 依赖 trim；patent 依赖 fos；trend 独立
    "n_fos":        ("a_trim",),
    "n_patent":     ("n_fos",),
    "n_trend":      (),
    # S 阶段：依赖所有前序产出
    "s_platform":   ("a_trim", "n_fos"),
    "s_costsystem": ("a_trim", "n_fos"),
}


def _load() -> dict[str, Any]:
    if not PLANS_DB.exists():
        return {}
    return json.loads(PLANS_DB.read_text(encoding="utf-8"))


def _save(db: dict[str, Any]) -> None:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    PLANS_DB.write_text(
        json.dumps(db, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_stage(product_key: str, stage: str) -> dict[str, Any] | None:
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    db = _load()
    return db.get(product_key, {}).get("stages", {}).get(stage)


def list_stages(product_key: str) -> dict[str, dict[str, Any]]:
    db = _load()
    return db.get(product_key, {}).get("stages", {})


def missing_deps(product_key: str, stage: str) -> list[str]:
    """返回该 stage 依赖但尚未跑过的前置 stage 列表。"""
    done = list_stages(product_key)
    return [d for d in STAGE_DEPS.get(stage, ()) if d not in done]


def save_stage(
    product_key: str,
    stage: str,
    data: dict[str, Any],
    md_text: str,
) -> Path:
    """写入结构化 JSON + 人类可读 markdown，返回 md 文件路径。"""
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")

    md_path = PLANS_DIR / product_key / f"{stage}.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8")

    db = _load()
    entry = db.setdefault(product_key, {"product_key": product_key, "stages": {}})
    entry["stages"][stage] = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "data": data,
        "report_path": str(md_path.relative_to(PLANS_DIR.parent.parent)),
    }
    _save(db)
    return md_path


def render_overview(product_key: str) -> Path:
    """把已完成阶段的 md 拼成 overview.md，返回路径。"""
    stages = list_stages(product_key)
    if not stages:
        raise FileNotFoundError(f"{product_key} 尚未跑过任何 PLANS 阶段")

    lines = [f"# {product_key} · PLANS 价值设计流程总览\n"]
    for s in STAGES:
        info = stages.get(s)
        if not info:
            lines.append(f"## {STAGE_TITLES[s]}\n\n_未执行_\n")
            continue
        md_path = PLANS_DIR.parent.parent / info["report_path"]
        body = md_path.read_text(encoding="utf-8") if md_path.exists() else "_报告文件缺失_"
        lines.append(f"## {STAGE_TITLES[s]}（{info['ran_at']}）\n")
        lines.append(body.strip())
        lines.append("")

    out = PLANS_DIR / product_key / "overview.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
