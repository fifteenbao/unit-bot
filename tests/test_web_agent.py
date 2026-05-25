from __future__ import annotations

import types
import unittest
from unittest import mock

from core import web_agent
from core import llm_runtime
from core.llm_runtime import LLMRuntime


class WebAgentTests(unittest.TestCase):
    def _runtime(self, *, server_tools: bool, model: str = "test-model"):
        captured: dict[str, object] = {}

        class FakeMessages:
            def create(self, **kwargs):
                captured.update(kwargs)
                return types.SimpleNamespace(
                    content=[types.SimpleNamespace(type="text", text="done")],
                    stop_reason="end_turn",
                )

        client = types.SimpleNamespace(messages=FakeMessages())
        runtime = LLMRuntime(
            client=client,
            model=model,
            backend="test",
            supports_server_web_tools=server_tools,
        )
        return runtime, captured

    def test_no_key_error_is_clear(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError) as cm:
                web_agent.run_web_agent("system", "user")
        self.assertIn("未配置统一 LLM 入口", str(cm.exception))
        self.assertIn("OPENCLAW_API_KEY", str(cm.exception))
        self.assertIn("ANTHROPIC_API_KEY", str(cm.exception))

    def test_run_web_agent_uses_server_tools_when_runtime_supports_them(self):
        runtime, captured = self._runtime(server_tools=True, model="claude-test")

        with mock.patch.object(web_agent, "make_runtime", return_value=runtime):
            result = web_agent.run_web_agent("system", "user")

        self.assertEqual(result, "done")
        self.assertEqual(captured["model"], "claude-test")
        tool_names = [tool["name"] for tool in captured["tools"]]
        self.assertEqual(tool_names, ["web_search", "web_fetch"])

    def test_run_web_agent_uses_client_tools_when_runtime_has_no_server_tools(self):
        runtime, captured = self._runtime(server_tools=False, model="openclaw-test")

        with mock.patch.object(web_agent, "make_runtime", return_value=runtime):
            result = web_agent.run_web_agent("system", "user")

        self.assertEqual(result, "done")
        self.assertEqual(captured["model"], "openclaw-test")
        tool_names = [tool["name"] for tool in captured["tools"]]
        self.assertEqual(tool_names, ["web_search", "web_fetch"])
        self.assertIn("input_schema", captured["tools"][0])

    def test_client_tools_call_search_helper(self):
        calls: list[str] = []

        class FakeMessages:
            def __init__(self):
                self.n = 0

            def create(self, **kwargs):
                self.n += 1
                if self.n == 1:
                    return types.SimpleNamespace(
                        content=[
                            types.SimpleNamespace(
                                type="tool_use",
                                name="web_search",
                                input={"query": "s20 teardown"},
                                id="call_1",
                            )
                        ],
                        stop_reason="tool_use",
                    )
                return types.SimpleNamespace(
                    content=[types.SimpleNamespace(type="text", text="final")],
                    stop_reason="end_turn",
                )

        runtime = LLMRuntime(
            client=types.SimpleNamespace(messages=FakeMessages()),
            model="openclaw-test",
            backend="openclaw",
            supports_server_web_tools=False,
        )

        with mock.patch.object(web_agent, "_client_web_search", side_effect=lambda q: calls.append(q) or "search result"):
            result = web_agent._run_web_agent_client_tools("system", "user", runtime=runtime)

        self.assertEqual(result, "final")
        self.assertEqual(calls, ["s20 teardown"])

    def test_anthropic_model_env_flows_through_unified_runtime(self):
        captured: dict[str, object] = {}

        class FakeMessages:
            def create(self, **kwargs):
                captured.update(kwargs)
                return types.SimpleNamespace(
                    content=[types.SimpleNamespace(type="text", text="done")],
                    stop_reason="end_turn",
                )

        class FakeAnthropicClient:
            def __init__(self, *args, **kwargs):
                self.messages = FakeMessages()

        with mock.patch.object(llm_runtime.anthropic, "Anthropic", FakeAnthropicClient), \
                mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test", "ANTHROPIC_MODEL": "claude-test"}, clear=True):
            result = web_agent.run_web_agent("system", "user")

        self.assertEqual(result, "done")
        self.assertEqual(captured["model"], "claude-test")


if __name__ == "__main__":
    unittest.main()
