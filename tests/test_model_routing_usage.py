"""Focused regression tests for explicit routing and fallback disclosure."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import model_router


class _Failing(model_router.BaseLLMClient):
    provider = "codex"
    model = "gpt-test"

    def complete(self, messages, system=None, max_tokens=2000):
        raise RuntimeError("provider unavailable")


class _Working(model_router.BaseLLMClient):
    provider = "glm"
    model = "glm-test"

    def complete(self, messages, system=None, max_tokens=2000):
        self.last_usage = {"prompt_tokens": 3, "completion_tokens": 2}
        return "ok"


class ModelRoutingUsageTests(unittest.TestCase):
    def test_missing_default_never_uses_legacy_environment(self):
        with patch("core.model_router.load_llm_config", return_value={
            "default_model": "", "task_overrides": {}, "fallback": [], "providers": {},
        }):
            with self.assertRaises(model_router.ModelRoutingNotConfigured):
                model_router.get_llm("simple")

    def test_disabled_provider_is_rejected_before_client_construction(self):
        cfg = {
            "default_model": "openrouter:test",
            "task_overrides": {}, "fallback": [],
            "providers": {"openrouter": {"enabled": False}},
        }
        with self.assertRaises(model_router.ModelProviderDisabled):
            model_router.build_client("openrouter:test", cfg)

    def test_fallback_exposes_requested_actual_and_reason(self):
        primary, fallback = _Failing(), _Working()
        primary._log_failure = lambda *args, **kwargs: None
        client = model_router.FallbackClient(
            [primary, fallback], requested_model="codex:gpt-test"
        )
        self.assertEqual(client.complete([]), "ok")
        self.assertEqual(client.requested_model, "codex:gpt-test")
        self.assertEqual(client.actual_model_id, "glm:glm-test")
        self.assertEqual(client.fallback_reason, "codex:RuntimeError")
        self.assertEqual(client.attempt_count, 2)

    def test_transport_fallback_is_bounded_to_one_extra_provider(self):
        cfg = {
            "default_model": "codex:primary",
            "task_overrides": {},
            "fallback": ["glm:first", "anthropic:second"],
            "providers": {},
        }
        built = [_Working(), _Working(), _Working()]
        with patch("core.model_router.load_llm_config", return_value=cfg), \
             patch("core.model_router.build_client", side_effect=built) as builder:
            client = model_router.get_llm("simple")
        self.assertEqual(len(client.clients), 2)
        self.assertEqual(builder.call_count, 2)

    def test_subscription_catalog_hides_platform_only_codex_models(self):
        provider = {
            "id": "codex", "label": "OpenAI Codex", "enabled": True,
            "needs_key": True, "key_present": True,
            "models": ["gpt-5.6-sol", "gpt-5.6"],
        }
        with patch("core.model_router.provider_catalog", return_value=[provider]), \
             patch.object(model_router.CodexClient, "uses_subscription_auth", return_value=True):
            models = {item["id"] for item in model_router.available_models()}
        self.assertIn("codex:gpt-5.6-sol", models)
        self.assertNotIn("codex:gpt-5.6", models)


if __name__ == "__main__":
    unittest.main()
