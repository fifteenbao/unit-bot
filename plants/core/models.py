"""Versioned business objects and cross-stage references."""
from __future__ import annotations

import re

ENTITY_TYPES = {"part", "function", "issue", "proposal"}
ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,95}")


def identifier(value):
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ValueError("对象 id 需以字母开头，仅含字母、数字、_.:-，最多 96 字符")
    return value


def text_field(obj, key):
    if not isinstance(obj.get(key), str) or not obj[key].strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return obj[key]


def objects(items, existing=None):
    if not isinstance(items, list):
        raise ValueError("entities 必须是数组")
    catalog = dict(existing or {})
    local_ids = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("业务对象必须是对象")
        key = identifier(item.get("id"))
        if key in local_ids:
            raise ValueError(f"重复业务 id：{key}")
        local_ids.add(key)
        if item.get("type") not in ENTITY_TYPES:
            raise ValueError("业务类型为 part/function/issue/proposal")
        text_field(item, "name")
        if key in catalog and catalog[key] != item:
            raise ValueError(f"同一业务 id 定义冲突：{key}，请修改其原始定义并重跑相关阶段")
        catalog[key] = item
    for item in catalog.values():
        refs = item.get("related_ids", [])
        if not isinstance(refs, list) or any(not isinstance(r, str) or r not in catalog for r in refs):
            raise ValueError(f"{item['id']} 的 related_ids 包含未知对象")
    return catalog


def evidence_catalog(items, existing=None):
    if not isinstance(items, list):
        raise ValueError("evidence 必须是数组")
    catalog = dict(existing or {})
    local_ids = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("证据必须是对象")
        key = identifier(item.get("id"))
        if key in local_ids:
            raise ValueError(f"重复证据 id：{key}")
        local_ids.add(key)
        for field in ("source", "claim", "date", "locator"):
            text_field(item, field)
        if item.get("kind") not in ("fact", "inference", "assumption"):
            raise ValueError("证据 kind 必须为 fact/inference/assumption")
        if key in catalog and catalog[key] != item:
            raise ValueError(f"同一证据 id 定义冲突：{key}")
        catalog[key] = item
    return catalog


def references(item, key, catalog, *, allow_empty=False):
    values = item.get(key)
    if not isinstance(values, list) or (not values and not allow_empty):
        raise ValueError(f"{key} 必须是{'可空' if allow_empty else '非空'}引用数组")
    for value in values:
        if not isinstance(value, str) or value not in catalog:
            raise ValueError(f"{key} 引用了未知对象：{value}")
    return values


def catalogs(project, upstream):
    entities = objects(project.get("entities", []))
    evidence = {}
    for result in upstream.values():
        entities = objects(result.get("entities", []), entities)
        evidence = evidence_catalog(result["evidence"], evidence)
    return entities, evidence
