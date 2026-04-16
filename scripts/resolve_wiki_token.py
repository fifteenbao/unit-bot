#!/usr/bin/env python3
"""
飞书 Wiki 多维表格 Token 解析工具

问题背景：
  多维表格嵌入在 Wiki 页面时，URL 格式为：
    https://xxx.feishu.cn/wiki/<wiki_token>
  而配置需要的是 /base/ 格式的 app_token，两者不同。

用法：
  python3 scripts/resolve_wiki_token.py \
    --app-id cli_xxx \
    --app-secret xxx \
    --wiki-url "https://vh4smebe3m.feishu.cn/wiki/AbCdEfGhIjKl"

  或直接传 wiki_token：
    python3 scripts/resolve_wiki_token.py \
      --app-id cli_xxx --app-secret xxx \
      --wiki-token AbCdEfGhIjKl
"""
import argparse
import re
import sys

import requests


def get_tenant_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 token 失败: {data}")
    return data["tenant_access_token"]


def resolve_wiki_token(tenant_token: str, wiki_token: str) -> dict:
    """通过 Wiki node token 获取实际的多维表格 app_token 和 table_id"""
    resp = requests.get(
        "https://open.feishu.cn/open-apis/wiki/v2/nodes",
        headers={"Authorization": f"Bearer {tenant_token}"},
        params={"token": wiki_token},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Wiki API 错误: {data}")
    node = data.get("data", {}).get("node", {})
    return node


def list_tables(tenant_token: str, app_token: str) -> list:
    """列出多维表格的所有数据表及其 table_id"""
    resp = requests.get(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables",
        headers={"Authorization": f"Bearer {tenant_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Bitable API 错误: {data}")
    return data.get("data", {}).get("items", [])


def main():
    parser = argparse.ArgumentParser(description="解析飞书 Wiki 多维表格 Token")
    parser.add_argument("--app-id",     required=True, help="飞书应用 App ID")
    parser.add_argument("--app-secret", required=True, help="飞书应用 App Secret")
    parser.add_argument("--wiki-url",   help="Wiki 页面完整 URL")
    parser.add_argument("--wiki-token", help="Wiki Token（从 URL 中提取）")
    args = parser.parse_args()

    # 提取 wiki_token
    wiki_token = args.wiki_token
    if not wiki_token and args.wiki_url:
        m = re.search(r"/wiki/([A-Za-z0-9]+)", args.wiki_url)
        if not m:
            print("❌ 无法从 URL 中提取 wiki token，请检查 URL 格式")
            sys.exit(1)
        wiki_token = m.group(1)

    if not wiki_token:
        print("❌ 请提供 --wiki-url 或 --wiki-token")
        sys.exit(1)

    print(f"🔍 Wiki Token: {wiki_token}")
    print("📡 正在获取 tenant_access_token ...")
    tenant_token = get_tenant_token(args.app_id, args.app_secret)

    print("📡 正在解析 Wiki 节点 ...")
    node = resolve_wiki_token(tenant_token, wiki_token)

    obj_type  = node.get("obj_type", "")
    obj_token = node.get("obj_token", "")

    if obj_type != "bitable":
        print(f"⚠️  此 Wiki 节点类型为 '{obj_type}'，不是多维表格（bitable）")
        print(f"   节点信息: {node}")
        sys.exit(1)

    print(f"\n✅ 解析成功！\n")
    print(f"   FEISHU_BITABLE_APP_TOKEN = {obj_token}")

    print("\n📋 正在获取数据表列表 ...")
    tables = list_tables(tenant_token, obj_token)
    if tables:
        print(f"\n   找到 {len(tables)} 张数据表：\n")
        for t in tables:
            print(f"   表名: {t.get('name')}")
            print(f"   Table ID: {t.get('table_id')}")
            print()
        print("💡 将以上 ID 填入 .env：")
        print(f"   FEISHU_BITABLE_APP_TOKEN={obj_token}")
        for t in tables:
            print(f"   # {t.get('name')}")
            print(f"   FEISHU_PRODUCTS_TABLE_ID={t.get('table_id')}   # 如果这是产品表")
    else:
        print("   未找到数据表，请确认多维表格内已创建数据表")


if __name__ == "__main__":
    main()
