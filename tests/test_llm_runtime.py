from __future__ import annotations

import sys
import types
import unittest
from unittest import mock


class LLMRuntimeTests(unittest.TestCase):
    def _load_runtime_with_fake_anthropic(self):
        class FakeAnthropicClient:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        fake_module = types.SimpleNamespace(Anthropic=FakeAnthropicClient)
        with mock.patch.dict(sys.modules, {"anthropic": fake_module}):
            import importlib
            import core.llm_runtime as runtime
            return importlib.reload(runtime)

    def test_openclaw_runtime_disables_server_web_tools(self):
        runtime = self._load_runtime_with_fake_anthropic()

        with mock.patch.dict("os.environ", {
            "OPENCLAW_API_KEY": "sk-openclaw",
            "OPENCLAW_BASE_URL": "https://example.test/v1",
            "OPENCLAW_MODEL": "openclaw-model",
        }, clear=True):
            cfg = runtime.make_runtime(require_key=True)

        self.assertEqual(cfg.backend, "openclaw")
        self.assertEqual(cfg.model, "openclaw-model")
        self.assertFalse(cfg.supports_server_web_tools)
        self.assertEqual(cfg.client.kwargs["api_key"], "sk-openclaw")
        self.assertEqual(cfg.client.kwargs["base_url"], "https://example.test/v1")

    def test_anthropic_runtime_supports_server_web_tools(self):
        runtime = self._load_runtime_with_fake_anthropic()

        with mock.patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "sk-ant",
            "ANTHROPIC_MODEL": "claude-test",
        }, clear=True):
            cfg = runtime.make_runtime(require_key=True)

        self.assertEqual(cfg.backend, "anthropic")
        self.assertEqual(cfg.model, "claude-test")
        self.assertTrue(cfg.supports_server_web_tools)

    def test_make_client_and_tools_filters_server_tools_for_openclaw(self):
        runtime = self._load_runtime_with_fake_anthropic()
        all_tools = [
            {"type": "web_search_20260209", "name": "web_search"},
            {"type": "web_fetch_20260209", "name": "web_fetch"},
            {"name": "list_products"},
        ]

        with mock.patch.dict("os.environ", {"OPENCLAW_API_KEY": "sk-openclaw"}, clear=True):
            _, tools, model = runtime.make_client_and_tools(all_tools)

        self.assertEqual(model, runtime.DEFAULT_MODEL)
        self.assertEqual(tools, [{"name": "list_products"}])


if __name__ == "__main__":
    unittest.main()
