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

# ── 配置读取 ───────────────────────────────────────────────────────

def _cfg():
    try:
        from core.config import (
            get_feishu_app_id, get_feishu_app_secret,
            get_feishu_product_obj_token, get_feishu_teardown_obj_token,
            get_feishu_components_obj_token,
        )
        return {
            "app_id":     get_feishu_app_id(),
            "app_secret": get_feishu_app_secret(),
            "product":    get_feishu_product_obj_token(),
            "teardown":   get_feishu_teardown_obj_token(),
            "components": get_feishu_components_obj_token(),
        }
    except Exception:
        return {
            "app_id":     os.getenv("FEISHU_APP_ID", ""),
            "app_secret": os.getenv("FEISHU_APP_SECRET", ""),
            "product":    os.getenv("FEISHU_PRODUCT_OBJ_TOKEN", ""),
            "teardown":   os.getenv("FEISHU_TEARDOWN_OBJ_TOKEN", ""),
            "components": os.getenv("FEISHU_COMPONENTS_OBJ_TOKEN", ""),
        }


_token_cache: dict[str, Any] = {}
_table_id_cache: dict[str, str] = {}   # app_token → first table_id


def _is_configured() -> bool:
    c = _cfg()
    return bool(c["app_id"] and c["app_secret"])


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


def _get_first_table_id(app_token: str, token: str) -> str:
    """自动获取多维表格的第一张数据表 ID（带进程内缓存）"""
    import requests
    if app_token in _table_id_cache:
        return _table_id_cache[app_token]
    try:
        resp = requests.get(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        items = resp.json().get("data", {}).get("items", [])
        table_id = items[0]["table_id"] if items else ""
        if table_id:
            _table_id_cache[app_token] = table_id
        return table_id
    except Exception as e:
        logger.warning(f"获取 table_id 失败 (app_token={app_token}): {e}")
        return ""


def _upsert_records(app_token: str, records: list[dict], key_field: str) -> int:
    """
    向飞书多维表格写入记录。app_token 即 config 中的 obj_token。
    table_id 自动取第一张表。返回成功写入条数。
    """
    import requests
    if not app_token or not _is_configured():
        return 0
    token = _get_token()
    if not token:
        return 0

    table_id = _get_first_table_id(app_token, token)
    if not table_id:
        logger.warning(f"未找到数据表 (app_token={app_token})")
        return 0

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    base_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"

    written = 0
    for i in range(0, len(records), 500):
        batch = records[i : i + 500]
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
    obj_token = _cfg()["teardown"]
    if not obj_token:
        return
    n = _upsert_records(obj_token, rows, key_field="name")
    if n:
        logger.info(f"飞书拆机同步 [{model}]: {n} 条")


def sync_components_lib(rows: list[dict]) -> None:
    """将标准件库同步到飞书标准件表"""
    obj_token = _cfg()["components"]
    if not obj_token:
        return
    n = _upsert_records(obj_token, rows, key_field="id")
    if n:
        logger.info(f"飞书标准件库同步: {n} 条")


def sync_product(product_key: str, entry: dict) -> None:
    """将产品数据同步到飞书产品数据库（由 agent.tool_save_product 调用）"""
    obj_token = _cfg()["product"]
    if not obj_token:
        return
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
    n = _upsert_records(obj_token, [flat], key_field="product_key")
    if n:
        logger.info(f"飞书产品同步 [{product_key}]")
