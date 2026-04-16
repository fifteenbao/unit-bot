#!/usr/bin/env python3
"""
BOM Agent 服务启动脚本
供 OpenClaw skill 系统调用：python3 scripts/start.py
"""
import os
import sys
from pathlib import Path

# 保证根目录在 path 中
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

if not os.getenv("ANTHROPIC_API_KEY"):
    print("❌ 未设置 ANTHROPIC_API_KEY，请在 .env 文件或环境变量中配置")
    sys.exit(1)

port = int(os.getenv("OPENCLAW_BOT_PORT", "8090"))
print(f"🤖 BOM Agent 启动中，端口 {port} …")

import openclaw_bot
openclaw_bot.app.run(host="0.0.0.0", port=port, debug=False)
