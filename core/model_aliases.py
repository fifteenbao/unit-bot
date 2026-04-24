"""
国内/海外型号双向模糊匹配

数据来源：data/products/model_aliases.json
用途：FCC ID.io 搜索时将国内型号转换为海外型号（FCC 以海外型号申报），
      以及将用户输入的海外型号规范化为国内型号（产品数据库主键）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NamedTuple

ALIASES_FILE = Path(__file__).parent.parent / "data" / "products" / "model_aliases.json"


class AliasMatch(NamedTuple):
    brand: str
    cn_model: str
    global_model: str
    score: float          # 0~1，越高越相似


def _normalize(s: str) -> str:
    """去空格、小写、去连字符，用于模糊比对"""
    return re.sub(r"[\s\-_]+", "", s).lower()


def _load() -> dict[str, list[dict]]:
    """加载映射表，统一成 {brand: [{cn_model, global_model, ...}]} 格式。"""
    if not ALIASES_FILE.exists():
        return {}
    data = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
    result: dict[str, list[dict]] = {}
    for k, v in data.items():
        if k.startswith("_"):
            continue
        # 兼容两种格式：list 或 {"aliases": [...], ...}
        if isinstance(v, list):
            result[k] = v
        elif isinstance(v, dict) and "aliases" in v:
            result[k] = v["aliases"]
    return result


def _score(query_norm: str, candidate_norm: str) -> float:
    """简单得分：完全匹配=1.0，包含=0.7，前缀=0.5，否则按公共前缀长度"""
    if query_norm == candidate_norm:
        return 1.0
    if query_norm in candidate_norm or candidate_norm in query_norm:
        # 长度比越接近分越高
        ratio = min(len(query_norm), len(candidate_norm)) / max(len(query_norm), len(candidate_norm))
        return 0.5 + 0.4 * ratio
    # 公共前缀
    common = 0
    for a, b in zip(query_norm, candidate_norm):
        if a == b:
            common += 1
        else:
            break
    if common == 0:
        return 0.0
    return 0.3 * common / max(len(query_norm), len(candidate_norm))


def find_alias(model_input: str, brand_hint: str | None = None, top_k: int = 3) -> list[AliasMatch]:
    """
    输入任意型号名（国内或海外），返回最相近的映射结果列表。
    brand_hint 可选，限定品牌范围（如 "Roborock"）加速匹配。
    """
    aliases = _load()
    query_norm = _normalize(model_input)
    results: list[AliasMatch] = []

    brands = [brand_hint] if brand_hint and brand_hint in aliases else list(aliases.keys())

    for brand in brands:
        for entry in aliases[brand]:
            cn_norm  = _normalize(entry["cn_model"])
            gl_norm  = _normalize(entry["global_model"])
            score = max(_score(query_norm, cn_norm), _score(query_norm, gl_norm))
            if score > 0.2:
                results.append(AliasMatch(
                    brand=brand,
                    cn_model=entry["cn_model"],
                    global_model=entry["global_model"],
                    score=round(score, 3),
                ))

    results.sort(key=lambda x: -x.score)
    return results[:top_k]


def cn_to_global(cn_model: str, brand_hint: str | None = None) -> str | None:
    """国内型号 → 海外型号（用于 FCC ID.io 搜索）。无匹配返回 None。"""
    matches = find_alias(cn_model, brand_hint)
    if matches and matches[0].score >= 0.8:
        return matches[0].global_model
    return None


def global_to_cn(global_model: str, brand_hint: str | None = None) -> str | None:
    """海外型号 → 国内型号（用于产品数据库 key 规范化）。无匹配返回 None。"""
    matches = find_alias(global_model, brand_hint)
    if matches and matches[0].score >= 0.8:
        return matches[0].cn_model
    return None
