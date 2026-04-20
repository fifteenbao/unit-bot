"""
数据源配置加载器

优先级：data/config.yaml > 环境变量（.env）
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

CONFIG_FILE = Path(__file__).parent.parent / "config.yaml"

_cache: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache

    cfg: dict[str, Any] = {"feishu": {}, "local": {}}
    if CONFIG_FILE.exists():
        try:
            import yaml
            raw = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
            cfg["feishu"] = raw.get("feishu") or {}
            cfg["local"]  = raw.get("local")  or {}
        except ImportError:
            # PyYAML 未安装时回退到环境变量
            pass

    _cache = cfg
    return cfg


def _str(val: Any) -> str:
    return str(val).strip() if val else ""


# ── 公开 API ──────────────────────────────────────────────────────

def get_feishu_app_id() -> str:
    v = _str(_load()["feishu"].get("app_id"))
    return v or os.getenv("FEISHU_APP_ID", "")


def get_feishu_app_secret() -> str:
    v = _str(_load()["feishu"].get("app_secret"))
    return v or os.getenv("FEISHU_APP_SECRET", "")


def get_feishu_product_obj_token() -> str:
    v = _str(_load()["feishu"].get("product_obj_token"))
    return v or os.getenv("FEISHU_PRODUCT_OBJ_TOKEN", "")


def get_feishu_teardown_obj_token() -> str:
    v = _str(_load()["feishu"].get("teardown_obj_token"))
    return v or os.getenv("FEISHU_TEARDOWN_OBJ_TOKEN", "")


def get_feishu_components_obj_token() -> str:
    v = _str(_load()["feishu"].get("components_obj_token"))
    return v or os.getenv("FEISHU_COMPONENTS_OBJ_TOKEN", "")


def get_local_product_xlsx() -> Path | None:
    v = _str(_load()["local"].get("product_xlsx"))
    path = Path(v) if v else None
    return path if (path and path.exists()) else None


def get_local_teardown_xlsx() -> Path | None:
    v = _str(_load()["local"].get("teardown_xlsx"))
    # 也兼容旧环境变量 BOM_EXCEL_FILE
    if not v:
        v = os.getenv("BOM_EXCEL_FILE", "")
    path = Path(v) if v else None
    return path if (path and path.exists()) else None


def reload() -> None:
    """强制重新读取配置文件（热更新用）"""
    global _cache
    _cache = None
