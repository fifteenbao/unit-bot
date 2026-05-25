from __future__ import annotations

import json
import sys
import types
import unittest
from unittest import mock

import httpx

from core import web_agent


class WebAgentTests(unittest.TestCase):
    def _patch_env(self, values: dict[str, str]):
        return mock.patch.object(
            web_agent,
            "_env",
            side_effect=lambda name, default="": values.get(name, default),
        )

    def test_no_key_error_is_clear(self):
        with self._patch_env({}):
            with self.assertRaises(RuntimeError) as cm:
                web_agent.run_web_agent("system", "user")
        self.assertIn("未配置 LLM API Key", str(cm.exception))
        self.assertIn("ANTHROPIC_API_KEY", str(cm.exception))

    def test_aihubmix_routes_to_openai_backend(self):
        with self._patch_env({"AIHUBMIX_API_KEY": "sk-test"}), \
                mock.patch.object(web_agent, "_run_web_agent_openai", return_value="openai") as openai_fn, \
                mock.patch.object(web_agent, "_run_web_agent_deepseek") as deepseek_fn, \
                mock.patch.object(web_agent, "_run_web_agent_anthropic") as anthropic_fn:
            result = web_agent.run_web_agent("system", "user")

        self.assertEqual(result, "openai")
        openai_fn.assert_called_once()
        deepseek_fn.assert_not_called()
        anthropic_fn.assert_not_called()

    def test_deepseek_routes_to_client_backend(self):
        with self._patch_env({"DEEPSEEK_API_KEY": "sk-test"}), \
                mock.patch.object(web_agent, "_run_web_agent_openai") as openai_fn, \
                mock.patch.object(web_agent, "_run_web_agent_deepseek", return_value="deepseek") as deepseek_fn, \
                mock.patch.object(web_agent, "_run_web_agent_anthropic") as anthropic_fn:
            result = web_agent.run_web_agent("system", "user")

        self.assertEqual(result, "deepseek")
        openai_fn.assert_not_called()
        deepseek_fn.assert_called_once()
        anthropic_fn.assert_not_called()

    def test_deepseek_client_calls_duckduckgo_helpers(self):
        responses = [
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "web_search",
                                        "arguments": json.dumps({"query": "s20 teardown"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "content": "final",
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        ]
        search_calls: list[str] = []
        fetch_calls: list[str] = []

        class FakeResponse:
            def __init__(self, payload: dict):
                self._payload = payload
                self.status_code = 200

            def json(self):
                return self._payload

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def post(self, *args, **kwargs):
                return FakeResponse(responses.pop(0))

        with self._patch_env({"DEEPSEEK_API_KEY": "sk-test"}), \
                mock.patch.object(web_agent, "_client_web_search", side_effect=lambda q: search_calls.append(q) or "search result"), \
                mock.patch.object(web_agent, "_client_web_fetch", side_effect=lambda url: fetch_calls.append(url) or "fetch result"), \
                mock.patch("httpx.Client", FakeClient):
            result = web_agent._run_web_agent_deepseek("system", "user")

        self.assertEqual(result, "final")
        self.assertEqual(search_calls, ["s20 teardown"])
        self.assertEqual(fetch_calls, [])

    def test_anthropic_uses_server_side_tools(self):
        captured: dict[str, object] = {}

        class FakeMessages:
            def create(self, **kwargs):
                captured.update(kwargs)
                return types.SimpleNamespace(
                    content=[types.SimpleNamespace(type="text", text="done")],
                    stop_reason="end_turn",
                )

        class FakeAnthropicClient:
            def __init__(self):
                self.messages = FakeMessages()

        fake_module = types.SimpleNamespace(Anthropic=FakeAnthropicClient)

        with self._patch_env({"ANTHROPIC_API_KEY": "sk-test"}), \
                mock.patch.dict(sys.modules, {"anthropic": fake_module}):
            result = web_agent._run_web_agent_anthropic("system", "user")

        self.assertEqual(result, "done")
        tool_names = [tool["name"] for tool in captured["tools"]]
        self.assertIn("web_search", tool_names)
        self.assertIn("web_fetch", tool_names)


if __name__ == "__main__":
    unittest.main()
