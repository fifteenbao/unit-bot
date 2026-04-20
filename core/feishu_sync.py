"""
飞书多维表格同步模块

环境变量配置：
  FEISHU_APP_ID               飞书开放平台 App ID
  FEISHU_APP_SECRET           飞书开放平台 App Secret
  FEISHU_PRODUCT_TABLE_URL    产品数据库表格链接
  FEISHU_TEARDOWN_TABLE_URL   拆机数据库表格链接
  FEISHU_COMPONENTS_TABLE_URL 标准件库表格链接

未配置时所有同步操作静默跳过，本地文件仍正常写入。
"""
from __future__ import annotations

import os
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── 配置读取（config.yaml 优先，回退环境变量）──────────────────────

def _cfg():
    try:
        from core.config import (
            get_feishu_product_url, get_feishu_teardown_url,
            get_feishu_components_url,
        )
        from core.config import _load
        raw = _load()
        feishu = raw.get("feishu", {})
        return {
            "app_id":     feishu.get("app_id") or os.getenv("FEISHU_APP_ID", ""),
            "app_secret": feishu.get("app_secret") or os.getenv("FEISHU_APP_SECRET", ""),
            "product":    get_feishu_product_url(),
            "teardown":   get_feishu_teardown_url(),
            "components": get_feishu_components_url(),
        }
    except Exception:
        return {
            "app_id":     os.getenv("FEISHU_APP_ID", ""),
            "app_secret": os.getenv("FEISHU_APP_SECRET", ""),
            "product":    os.getenv("FEISHU_PRODUCT_TABLE_URL", ""),
            "teardown":   os.getenv("FEISHU_TEARDOWN_TABLE_URL", ""),
            "components": os.getenv("FEISHU_COMPONENTS_TABLE_URL", ""),
        }


_token_cache: dict[str, Any] = {}
_wiki_resolved: dict[str, str] = {}   # wiki_token → app_token


def _is_configured() -> bool:
    c = _cfg()
    return bool(c["app_id"] and c["app_secret"])


def _resolve_wiki_url(url: str) -> str | None:
    """
    将 /wiki/ 格式 URL 解析为 /base/ 格式 app_token。
    需要 app_id / app_secret 已配置，结果缓存在进程内。
    """
    import requests
    m = re.search(r"/wiki/([A-Za-z0-9]+)", url)
    if not m:
        return None
    wiki_token = m.group(1)
    if wiki_token in _wiki_resolved:
        return _wiki_resolved[wiki_token]

    token = _get_token()
    if not token:
        return None
    try:
        resp = requests.get(
            "https://open.feishu.cn/open-apis/wiki/v2/nodes",
            headers={"Authorization": f"Bearer {token}"},
            params={"token": wiki_token},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            logger.warning(f"Wiki 解析失败: {data.get('msg')} (wiki_token={wiki_token})")
            return None
        obj_token = data["data"]["node"].get("obj_token")
        if obj_token:
            _wiki_resolved[wiki_token] = obj_token
        return obj_token
    except Exception as e:
        logger.warning(f"Wiki URL 解析异常: {e}")
        return None


def _parse_table_url(url: str) -> tuple[str, str, str] | None:
    """
    从飞书表格链接解析 (host, app_token, table_id)。
    支持：
      /base/{app_token}?table={table_id}   — 多维表格直链
      /wiki/{wiki_token}?sheet={sheet_id}  — Wiki 嵌入（自动解析，需 API 凭证）
    """
    if not url:
        return None

    host_m = re.match(r"(https?://[^/]+)", url)
    host = host_m.group(1) if host_m else "https://open.feishu.cn"

    # /base/ 直链
    m = re.search(r"/base/([A-Za-z0-9]+)", url)
    if m:
        app_token = m.group(1)
        t = re.search(r"[?&]table=([A-Za-z0-9_]+)", url)
        return host, app_token, t.group(1) if t else ""

    # /wiki/ 格式 — 需要 API 凭证解析
    if "/wiki/" in url:
        if not _is_configured():
            logger.warning(
                "飞书链接为 Wiki 格式，需在 config.yaml 填写 feishu.app_id / app_secret 才能同步"
            )
            return None
        app_token = _resolve_wiki_url(url)
        if not app_token:
            return None
        # sheet= 参数映射为 table_id（用于区分同一 wiki 下多张表）
        t = re.search(r"[?&]sheet=([A-Za-z0-9_]+)", url)
        return host, app_token, t.group(1) if t else ""

    return None


def _get_token() -> str | None:
    """获取 tenant_access_token（带简单缓存）"""
    import time, requests
    cached = _token_cache.get("token")
    exp    = _token_cache.get("expires_at", 0)
    if cached and time.time() < exp - 60:
        return cached
    c = _cfg()
    if not c["app_id"] or not c["app_secret"]:
        return None
    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": c["app_id"], "app_secret": c["app_secret"]},
            timeout=10,
        )
        data = resp.json()
        token = data.get("tenant_access_token")
        if token:
            _token_cache["token"] = token
            _token_cache["expires_at"] = time.time() + data.get("expire", 7200)
        return token
    except Exception as e:
        logger.warning(f"飞书 token 获取失败: {e}")
        return None


def _upsert_records(table_url: str, records: list[dict], key_field: str) -> int:
    """
    向飞书多维表格写入记录（按 key_field 去重 upsert）。
    返回成功写入条数，失败时返回 0。
    """
    import requests
    if not _is_configured():
        return 0
    parsed = _parse_table_url(table_url)
    if not parsed:
        logger.warning(f"无法解析飞书表格链接: {table_url}")
        return 0
    host, app_token, table_id = parsed
    token = _get_token()
    if not token:
        return 0

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    base_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"

    # 批量写入（每批 500 条）
    written = 0
    batch_size = 500
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        payload = {"records": [{"fields": r} for r in batch]}
        try:
            resp = requests.post(
                f"{base_url}/batch_create",
                headers=headers,
                json=payload,
                timeout=30,
            )
            result = resp.json()
            if result.get("code") == 0:
                written += len(batch)
            else:
                logger.warning(f"飞书写入失败: {result.get('msg')} (code={result.get('code')})")
        except Exception as e:
            logger.warning(f"飞书请求异常: {e}")

    return written


# ── 公开同步接口 ────────────────────────────────────────────────

def sync_teardown(model: str, rows: list[dict]) -> None:
    """将单机型拆机数据同步到飞书拆机数据库"""
    url = _cfg()["teardown"]
    if not url:
        return
    n = _upsert_records(url, rows, key_field="name")
    if n:
        logger.info(f"飞书拆机同步 [{model}]: {n} 条")


def sync_components_lib(rows: list[dict]) -> None:
    """将标准件库同步到飞书标准件表"""
    url = _cfg()["components"]
    if not url:
        return
    n = _upsert_records(url, rows, key_field="id")
    if n:
        logger.info(f"飞书标准件库同步: {n} 条")


def sync_product(product_key: str, entry: dict) -> None:
    """将产品数据同步到飞书产品数据库（由 agent.tool_save_product 调用）"""
    if not _cfg()["product"]:
        return
    import json
    flat = {
        "product_key":    product_key,
        "brand":          entry.get("brand", ""),
        "model_name":     entry.get("model_name", ""),
        "retail_price":   entry.get("retail_price_cny"),
        "release_date":   entry.get("release_date", ""),
        "market_segment": entry.get("market_segment", ""),
        "suction_pa":     entry.get("specs", {}).get("suction_power_pa"),
        "obstacle_cm":    entry.get("specs", {}).get("obstacle_height_cm"),
        "battery_mah":    entry.get("specs", {}).get("battery_capacity_mah"),
        "navigation":     entry.get("specs", {}).get("navigation", ""),
        "bom_source":     entry.get("bom_cost", {}).get("bom_source", ""),
        "last_updated":   entry.get("data_sources", {}).get("last_updated", ""),
        "notes":          entry.get("notes", ""),
    }
    n = _upsert_records(PRODUCT_TABLE_URL, [flat], key_field="product_key")
    if n:
        logger.info(f"飞书产品同步 [{product_key}]")
