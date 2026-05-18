"""process_lib — 工艺/模具/工具库接入层。

从三个 CSV 读取 Should Cost 五要素中的 ②加工成本 ③模具摊销 ④工具折旧：

  data/lib/processes.csv  —— 工艺基线（注塑/CNC/电镀/PCB/SMT/线束 等，仓库自带 22 条种子）
  data/lib/molds.csv      —— 模具摊销（按用户内部脱敏编号 mold_id 维护，仓库自带 25 条种子）
  data/lib/tooling.csv    —— 夹具/刀具折旧（仓库自带 21 条种子）

⚠️ 三个 CSV 都在 .gitignore 范围（data/lib/），不会进 git；用户在本地按自己的厂商数据填充。
为 agent.py 的 query_processes / query_molds / query_tooling 提供数据。
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

_BASE = Path(__file__).parent.parent / "data" / "lib"
_PROCESSES = _BASE / "processes.csv"
_MOLDS = _BASE / "molds.csv"
_TOOLING = _BASE / "tooling.csv"


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def _processes() -> list[dict]:
    return _load(_PROCESSES)


@lru_cache(maxsize=1)
def _molds() -> list[dict]:
    return _load(_MOLDS)


@lru_cache(maxsize=1)
def _tooling() -> list[dict]:
    return _load(_TOOLING)


def query_processes(
    keyword: str | None = None,
    category: str | None = None,
    process_id: str | None = None,
) -> list[dict]:
    rows = _processes()
    out = []
    for r in rows:
        if process_id and r.get("process_id") != process_id:
            continue
        if category and category not in r.get("category", ""):
            continue
        if keyword:
            hay = " ".join([
                r.get("name", ""), r.get("sub_category", ""),
                r.get("applicable_materials", ""), r.get("note", ""),
            ])
            if keyword.lower() not in hay.lower():
                continue
        out.append(r)
    return out


def query_molds(
    keyword: str | None = None,
    mold_id: str | None = None,
    bucket: str | None = None,
) -> list[dict]:
    rows = _molds()
    out = []
    for r in rows:
        if mold_id and r.get("mold_id") != mold_id:
            continue
        if bucket and bucket not in r.get("bucket", ""):
            continue
        if keyword:
            hay = " ".join([
                r.get("mold_id", ""), r.get("related_parts", ""), r.get("note", ""),
            ])
            if keyword.lower() not in hay.lower():
                continue
        out.append(r)
    return out


def query_tooling(
    keyword: str | None = None,
    category: str | None = None,
    bound_process: str | None = None,
) -> list[dict]:
    rows = _tooling()
    out = []
    for r in rows:
        if bound_process and r.get("bound_process") != bound_process:
            continue
        if category and category not in r.get("category", ""):
            continue
        if keyword:
            hay = " ".join([
                r.get("name", ""), r.get("applicable_parts", ""), r.get("note", ""),
            ])
            if keyword.lower() not in hay.lower():
                continue
        out.append(r)
    return out
