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

# ── 配置读取 ────────────────────────────────────────────────────

APP_ID     = os.getenv("FEISHU_APP_ID", "")
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

PRODUCT_TABLE_URL    = os.getenv("FEISHU_PRODUCT_TABLE_URL", "")
TEARDOWN_TABLE_URL   = os.getenv("FEISHU_TEARDOWN_TABLE_URL", "")
COMPONENTS_TABLE_URL = os.getenv("FEISHU_COMPONENTS_TABLE_URL", "")

_token_cache: dict[str, Any] = {}


def _is_configured() -> bool:
    return bool(APP_ID and APP_SECRET)


def _parse_table_url(url: str) -> tuple[str, str, str] | None:
    """
    从飞书表格链接解析 (host, app_token, table_id)
    支持格式：https://xxx.feishu.cn/base/{app_token}?table={table_id}
    """
    if not url:
        return None
    m = re.search(r"/base/([A-Za-z0-9]+)", url)
    if not m:
        return None
    app_token = m.group(1)
    t = re.search(r"[?&]table=([A-Za-z0-9_]+)", url)
    table_id = t.group(1) if t else ""
    host_m = re.match(r"(https?://[^/]+)", url)
    host = host_m.group(1) if host_m else "https://open.feishu.cn"
    return host, app_token, table_id


def _get_token() -> str | None:
    """获取 tenant_access_token（带简单缓存）"""
    import time, requests
    cached = _token_cache.get("token")
    exp    = _token_cache.get("expires_at", 0)
    if cached and time.time() < exp - 60:
        return cached
    try:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": APP_ID, "app_secret": APP_SECRET},
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
    if not TEARDOWN_TABLE_URL:
        return
    n = _upsert_records(TEARDOWN_TABLE_URL, rows, key_field="name")
    if n:
        logger.info(f"飞书拆机同步 [{model}]: {n} 条")


def sync_components_lib(rows: list[dict]) -> None:
    """将标准件库同步到飞书标准件表"""
    if not COMPONENTS_TABLE_URL:
        return
    n = _upsert_records(COMPONENTS_TABLE_URL, rows, key_field="id")
    if n:
        logger.info(f"飞书标准件库同步: {n} 条")


def sync_product(product_key: str, entry: dict) -> None:
    """将产品数据同步到飞书产品数据库（由 agent.tool_save_product 调用）"""
    if not PRODUCT_TABLE_URL:
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
