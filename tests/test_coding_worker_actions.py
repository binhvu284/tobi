"""Coding-model action parsing, repair, escalation, and active probe contracts."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.coding_workers import (  # noqa: E402
    BrokeredLLMWorker,
    CodingWorkerRouter,
    CodingWorkerUnavailable,
    _failure_detail,
    _json_object,
)


class FakeClient:
    def __init__(self, responses, model="fake:model") -> None:
        self.responses = list(responses)
        self.model = model
        self.calls = 0

    def complete(self, messages, system=None, max_tokens=2000):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakePolicy:
    data = {"workers": {"llm_tool_steps": 4}}


class FakeBroker:
    def __init__(self, *args, **kwargs) -> None:
        self.validation_commands = []


class CodingWorkerActionTests(unittest.TestCase):
    def test_parser_extracts_final_action_after_reasoning_objects(self) -> None:
        raw = '<think>{"note":"inspect first"}</think>\n```json\n' \
              '{"action":"complete","summary":"done","evidence":[]}\n```'
        self.assertEqual(_json_object(raw)["action"], "complete")

    def test_first_malformed_action_is_repaired_without_crashing(self) -> None:
        primary = FakeClient([
            "I will inspect the repository first.",
            '{"action":"complete","summary":"repaired","evidence":[]}',
        ], model="glm:glm-5.2")
        observed = []
        with patch("core.model_router.get_llm", return_value=primary), \
             patch("core.model_router.get_escalation_llm", return_value=(None, None)), \
             patch("core.coding_workers.CodingToolBroker", FakeBroker):
            result = BrokeredLLMWorker(FakePolicy()).run(
                1, "code", ROOT, {"preferred_models": ["glm:glm-5.2"]},
                on_event=lambda kind, payload: observed.append((kind, payload)),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(primary.calls, 2)
        self.assertIn("action_rejected", [kind for kind, _ in observed])

    def test_failed_repair_escalates_once_to_configured_model(self) -> None:
        primary = FakeClient(["not json", "still not json"], model="glm:glm-5.2")
        stronger = FakeClient([
            '{"action":"complete","summary":"fallback complete","evidence":[]}'
        ], model="openrouter:code")
        observed = []
        with patch("core.model_router.get_llm", return_value=primary), \
             patch(
                 "core.model_router.get_escalation_llm",
                 return_value=(stronger, "openrouter:code"),
             ), \
             patch("core.coding_workers.CodingToolBroker", FakeBroker):
            result = BrokeredLLMWorker(FakePolicy()).run(
                2, "code", ROOT, {"preferred_models": ["glm:glm-5.2"]},
                on_event=lambda kind, payload: observed.append((kind, payload)),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(stronger.calls, 1)
        escalations = [payload for kind, payload in observed if kind == "model_escalated"]
        self.assertEqual(escalations[0]["to_model"], "openrouter:code")

    def test_exhausted_recovery_reports_actionable_sanitized_detail(self) -> None:
        primary = FakeClient([
            ValueError("token=ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"),
            ValueError("provider rejected structured output"),
        ])
        with patch("core.model_router.get_llm", return_value=primary), \
             patch("core.model_router.get_escalation_llm", return_value=(None, None)), \
             patch("core.coding_workers.CodingToolBroker", FakeBroker):
            with self.assertRaises(CodingWorkerUnavailable) as captured:
                BrokeredLLMWorker(FakePolicy()).run(3, "code", ROOT, {})

        self.assertIn("provider rejected structured output", str(captured.exception))
        self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUVWXYZ", _failure_detail(ValueError(
            "token=ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
        )))

    def test_active_probe_requires_a_real_structured_handshake(self) -> None:
        client = FakeClient([
            '<think>ready</think>{"action":"complete","summary":"ready","evidence":[]}'
        ], model="glm-5.2")
        with patch("core.model_router.load_llm_config", return_value={}), \
             patch("core.model_router.build_client", return_value=client):
            status, detail = CodingWorkerRouter._active_model_probe("glm:glm-5.2")

        self.assertEqual(status, "ready")
        self.assertIn("handshake passed", detail)


if __name__ == "__main__":
    unittest.main()
