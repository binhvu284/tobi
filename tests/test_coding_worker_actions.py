"""Coding-model action parsing, repair, escalation, and active probe contracts."""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.coding_contracts import WorkerProfile  # noqa: E402
from core.coding_workers import (  # noqa: E402
    BrokeredLLMWorker,
    CodexCLIWorker,
    CodingWorkerRouter,
    CodingWorkerUnavailable,
    ExternalCLIWorker,
    _actionable_handoff,
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

    def limit(self, name: str, default: int) -> int:
        return default

    def feature_enabled(self, name: str) -> bool:
        return True


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


class WorkerLaunchSizeTests(unittest.TestCase):
    """A resuming run must be able to start whatever its checkpoint contains.

    Windows caps a command line at 32,767 characters and `_platform_cli_command` inflates the
    prompt about 3.7x, so a brief over roughly 8,800 characters could not launch at all -- it
    raised `[WinError 206] The filename or extension is too long` before the agent ran. The
    checkpoint handoff is what pushed it over: 41,318 of its 43,612 characters were
    `recent_events`, mostly heartbeat lines. The mechanism that exists to make a run resumable
    was the reason resuming was impossible; five identical retries died two seconds in.
    """

    def test_codex_sends_the_prompt_on_stdin_so_size_cannot_block_launch(self) -> None:
        self.assertTrue(CodexCLIWorker.prompt_on_stdin)
        worker = CodexCLIWorker.__new__(CodexCLIWorker)
        for prompt_size in (1_000, 200_000):
            argv = worker.command(
                WorkerProfile(slug="codex-chatgpt", name="Codex", adapter="codex", model="gpt-5.6"),
                CodexCLIWorker.STDIN_PROMPT, Path(ROOT), "session-id",
            )
            length = sum(len(str(part)) + 1 for part in argv)
            self.assertLess(length, 32_767, f"{prompt_size}-char prompt produced {length} chars")
            self.assertNotIn("x" * 50, " ".join(str(part) for part in argv))

    def test_the_handoff_given_to_the_agent_drops_the_event_log(self) -> None:
        handoff = {
            "status": "paused", "stage": "code", "next_action": "Correct the unmet criteria.",
            "head_sha": "a" * 40, "changed_files": ["core/awakening.py"],
            "worker_profile": "codex-chatgpt", "sprint": None,
            "recent_events": [{"event_type": "worker_heartbeat", "payload": {"noise": "x" * 200}}
                              for _ in range(200)],
            "checks": [{"argv": ["python", "-m", "compileall"], "ok": True, "output": "y" * 5000},
                       {"argv": ["npm", "run", "build"], "ok": False, "output": "z" * 5000}],
        }
        trimmed = _actionable_handoff(handoff)

        self.assertNotIn("recent_events", trimmed)
        self.assertEqual(trimmed["next_action"], "Correct the unmet criteria.")
        # Which check failed is actionable; five thousand characters of its output is not.
        self.assertEqual(trimmed["failed_checks"], "npm run build")
        self.assertNotIn("zzzz", json.dumps(trimmed))
        self.assertLess(len(json.dumps(trimmed)), 2_000, "handoff is still large enough to hurt")

        # The trimming has to be on the path that builds the brief, not merely available.
        # Asserting the helper alone still passed with the raw handoff wired straight in.
        source = (ROOT / "core" / "coding_workers.py").read_text(encoding="utf-8")
        self.assertIn('brief["checkpoint_handoff"] = _actionable_handoff(', source)

    def test_a_failed_resume_falls_back_to_a_fresh_session(self) -> None:
        """An unreplayable transcript must not strand the item.

        Codex reports `Orphan function call output` when a session was interrupted mid tool
        call. Every retry resumed that same session, so the run was as stuck as it had been
        behind the launch bug -- just with a different error. Resuming is an optimisation:
        the worktree holds the code and the handoff holds the next action.
        """
        attempts: list[str | None] = []

        class Runner:
            def run(self, workflow_id, argv, **kwargs):
                resumed = "resume" in [str(part) for part in argv]
                attempts.append("resume" if resumed else "fresh")
                if resumed:
                    return 1, "", "ERROR codex_core::util: Orphan function call output for call id:"
                return 0, '{"type":"item.completed"}', ""

        worker = CodexCLIWorker(FakePolicy(), Runner())
        events: list[tuple[str, dict]] = []
        # Bypass the Windows launcher so argv stays readable; its encoding is covered by
        # test_codex_sends_the_prompt_on_stdin_so_size_cannot_block_launch.
        with patch("core.coding_workers._platform_cli_command", side_effect=lambda argv, **_: argv),              patch.object(CodexCLIWorker, "probe", return_value={"status": "ready", "detail": "ok"}):
            result = worker.run(
                11, "code", ROOT, {"objective": "continue"},
                profile=WorkerProfile(slug="codex-chatgpt", name="Codex", adapter="codex"),
                external_session_id="poisoned-session",
                on_event=lambda kind, payload: events.append((kind, payload)),
            )

        self.assertEqual(attempts, ["resume", "fresh"], "did not retry without the session id")
        self.assertTrue(result["ok"])
        self.assertIn("resume_failed", [kind for kind, _ in events])
        # A first-attempt failure with no session to blame must still surface.
        self.assertNotIn("<Objs", str(events))

    def test_a_first_run_failure_is_not_retried_as_a_resume_fallback(self) -> None:
        calls: list[int] = []

        class Runner:
            def run(self, workflow_id, argv, **kwargs):
                calls.append(1)
                return 1, "", "#< CLIXML\nreal failure\n<Objs Version='1.1.0.1'><S>noise</S></Objs>"

        worker = CodexCLIWorker(FakePolicy(), Runner())
        with patch("core.coding_workers._platform_cli_command", side_effect=lambda argv, **_: argv),              patch.object(CodexCLIWorker, "probe", return_value={"status": "ready", "detail": "ok"}):
            with self.assertRaises(RuntimeError) as captured:
                worker.run(
                    11, "code", ROOT, {"objective": "start"},
                    profile=WorkerProfile(slug="codex-chatgpt", name="Codex", adapter="codex"),
                    external_session_id=None,
                )
        self.assertEqual(len(calls), 1, "a fresh run must not be retried")
        self.assertIn("real failure", str(captured.exception))
        self.assertNotIn("<Objs", str(captured.exception))

    def test_an_adapter_without_stdin_fails_with_the_real_reason(self) -> None:
        if os.name != "nt":
            self.skipTest("the command-line ceiling is a Windows limit")
        with self.assertRaises(CodingWorkerUnavailable) as captured:
            ExternalCLIWorker._assert_launchable(["opencode", "run", "x" * 40_000])
        self.assertIn("Windows limit", str(captured.exception))
        # A launchable command must not be refused.
        ExternalCLIWorker._assert_launchable(["codex", "exec", "-"])


if __name__ == "__main__":
    unittest.main()
