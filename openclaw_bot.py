"""
OpenClaw Bot 适配器
https://openclaw.ai / https://docs.openclaw.ai/automation/webhook

工作原理：
  1. 在本地运行 OpenClaw（npx openclaw）
  2. 在 openclaw config 里添加一个 Webhook Tool，指向本服务的 /hooks/agent
  3. 用户在 Slack / WhatsApp / Telegram 等 @ OpenClaw，触发 OpenClaw 调用本服务
  4. 本服务调用 BOM Agent，将结果以纯文本返回给 OpenClaw
  5. OpenClaw 将结果发回用户所在频道

部署方式：
  python openclaw_bot.py            # 开发模式
  gunicorn openclaw_bot:app         # 生产模式

OpenClaw 配置（~/.openclaw/config.yaml）示例：
  tools:
    - name: BOM Agent
      description: 扫地机器人 BOM 成本分析与技术选型
      type: webhook
      url: http://localhost:8090/hooks/agent
      secret: your_shared_secret   # 与 OPENCLAW_WEBHOOK_SECRET 对应

环境变量：
  OPENCLAW_WEBHOOK_SECRET   共享密钥，用于验证请求来自 OpenClaw（留空则跳过验证）
  OPENCLAW_BOT_PORT         服务监听端口，默认 8090
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from threading import Thread

from flask import Flask, request, jsonify

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

WEBHOOK_SECRET = os.getenv("OPENCLAW_WEBHOOK_SECRET", "")
BOT_PORT       = int(os.getenv("OPENCLAW_BOT_PORT", "8090"))

# ── 对话历史（按 session_id / channel 隔离）────────────────────────
_conversations: dict[str, list[dict]] = {}
MAX_HISTORY = 20


def _get_conversation(session_id: str) -> list[dict]:
    if session_id not in _conversations:
        _conversations[session_id] = []
    return _conversations[session_id]


def _trim_history(session_id: str) -> None:
    hist = _conversations.get(session_id, [])
    if len(hist) > MAX_HISTORY * 2:
        _conversations[session_id] = hist[-(MAX_HISTORY * 2):]


# ── 请求签名验证 ──────────────────────────────────────────────────

def _verify_signature(body: bytes) -> bool:
    """OpenClaw 用 X-OpenClaw-Signature: sha256=<hmac> 头部验签"""
    if not WEBHOOK_SECRET:
        return True
    sig_header = request.headers.get("X-OpenClaw-Signature", "")
    if not sig_header.startswith("sha256="):
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(sig_header[7:], expected)


# ── Agent 调用 ────────────────────────────────────────────────────

def _load_agent():
    """加载根目录 agent.py 的 run_query 函数"""
    spec = importlib.util.spec_from_file_location("agent", ROOT / "agent.py")
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 路由 ──────────────────────────────────────────────────────────

@app.route("/hooks/agent", methods=["POST"])
def hooks_agent():
    """
    OpenClaw Webhook Tool 入口。

    OpenClaw 发送的请求体（参考官方文档）：
    {
        "message":   "用户输入的问题",
        "agentId":   "...",          # OpenClaw 内部 Agent ID
        "channel":   "slack",        # 来源频道
        "sessionId": "...",          # 会话 ID（可选）
        "thinking":  "enabled"       # OpenClaw 透传字段（忽略）
    }

    返回格式（OpenClaw 读取 `result` 字段作为最终回复）：
    {
        "result": "Agent 的回答"
    }
    """
    raw_body = request.get_data()

    if not _verify_signature(raw_body):
        logger.warning("签名验证失败，拒绝请求")
        return jsonify({"error": "invalid signature"}), 403

    try:
        payload: dict = json.loads(raw_body)
    except json.JSONDecodeError:
        return jsonify({"error": "invalid JSON"}), 400

    message    = payload.get("message", "").strip()
    session_id = payload.get("sessionId") or payload.get("agentId", "default")
    channel    = payload.get("channel", "unknown")

    if not message:
        return jsonify({"result": ""}), 200

    logger.info(f"[{channel}/{session_id}] 收到: {message[:80]}")

    try:
        agent_mod    = _load_agent()
        conversation = _get_conversation(session_id)
        answer       = agent_mod.run_query(message, conversation)
        _trim_history(session_id)
    except Exception as e:
        logger.exception(f"Agent 处理失败: {e}")
        return jsonify({"result": f"处理出错：{e}"}), 500

    return jsonify({"result": answer})


@app.route("/health")
def health():
    import time
    return jsonify({"status": "ok", "timestamp": int(time.time())})


if __name__ == "__main__":
    logger.info(f"OpenClaw Bot 启动，监听 0.0.0.0:{BOT_PORT}")
    app.run(host="0.0.0.0", port=BOT_PORT, debug=False)
