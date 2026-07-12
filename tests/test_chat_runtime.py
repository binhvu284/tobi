from __future__ import annotations

import tempfile
import unittest
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import agent_runs, chat_runtime, chat_store, context_manager, database, model_router, tool_registry
from core.chat_runtime_contracts import ToolCall, TurnRequest


def request(message: str, mode: str = "chat", **capabilities) -> TurnRequest:
    return TurnRequest(session_id=1, message=message, mode=mode, capabilities=capabilities)


class ChatRuntimeTests(unittest.TestCase):
    def setUp(self):
        self._db_path = database.DB_PATH
        self._tmp = tempfile.TemporaryDirectory(dir=".tobi")
        database.DB_PATH = self._tmp.name + "/runtime.db"
        context_manager.invalidate()

    def tearDown(self):
        database.DB_PATH = self._db_path
        context_manager.invalidate()
        self._tmp.cleanup()

    def test_hybrid_routes_fast_and_scoped(self):
        self.assertEqual(chat_runtime.route_turn(request("hello"), "SMALLTALK").route, "direct")
        coding_chat = chat_runtime.route_turn(request("help me debug this code"), "CODING")
        self.assertEqual((coding_chat.route, coding_chat.max_tool_steps), ("direct", 0))
        mutation = chat_runtime.route_turn(request("create a task in TOBI"), "PROJECT_MGMT")
        self.assertTrue(mutation.requires_clarification)
        agent_action = chat_runtime.route_turn(request("create a task in TOBI", "agent"), "PROJECT_MGMT")
        self.assertEqual(agent_action.route, "action")
        self.assertEqual(set(agent_action.allowed_tools), {"list_projects", "create_task"})
        agent_code = chat_runtime.route_turn(request("implement the API fix", "agent"), "CODING")
        self.assertIn("run_command", agent_code.allowed_tools)

    def test_context_manifest_is_budgeted_and_marks_untrusted_project(self):
        manifest = context_manager.build_manifest(
            "status of Project Alpha", "chat",
            [{"role": "user", "content": "Earlier constraint"}],
            {"context_text": "Project Alpha resource text", "projects": [{"id": 1, "name": "Alpha"}]},
        )
        self.assertLessEqual(manifest.total_tokens, manifest.token_budget)
        self.assertEqual(manifest.token_budget, 6000)
        project = next(item for item in manifest.items if item.source == "project")
        self.assertEqual(project.trust, "untrusted")
        self.assertIn("Project Alpha", context_manager.prompt_context(manifest))

    def test_turn_trace_is_ordered_and_redacted(self):
        req = request("hello")
        recorder = chat_runtime.TurnRecorder.start(req, chat_runtime.route_turn(req, "SMALLTALK"))
        first = recorder.event("turn_started", "gateway", {"token": "secret-value"})
        recorder.set_context({"total_tokens": 4, "items": [{"source": "project", "content": "private text"}]})
        recorder.event("delta", "response", {"chars": 4})
        recorder.complete("done")
        trace = chat_runtime.get_trace(recorder.turn_id)
        self.assertEqual([e["seq"] for e in trace["events"]], [1, 2])
        self.assertEqual(first["data"]["token"], "[REDACTED]")
        self.assertIsNotNone(trace["first_event_ms"])
        self.assertIsNotNone(trace["first_token_ms"])
        self.assertNotIn("message", trace["request"])
        self.assertNotIn("content", trace["context"]["items"][0])

    def test_recovery_commands_keep_same_run(self):
        run_id = agent_runs.create_run(12, "test")
        agent_runs.set_status(run_id, "waiting_user", "failed step")
        result = agent_runs.command_run(run_id, "retry_step")
        self.assertEqual(result["run_id"], run_id)
        self.assertTrue(result["requires_turn"])
        self.assertEqual(agent_runs.get_run(run_id)["status"], "running")
        cancelled = agent_runs.command_run(run_id, "cancel")
        self.assertEqual(cancelled["run_id"], run_id)
        self.assertEqual(agent_runs.get_run(run_id)["status"], "cancelled")

    def test_tool_validation_and_idempotent_receipt(self):
        calls = []

        def mutate(value: int = 0, **_):
            calls.append(value)
            return {"ok": True, "value": value}

        spec = tool_registry.make_spec("mutate", mutate, "test", "low")
        invalid = tool_registry.validate_call({"tool": "mutate", "args": {"value": "bad"}}, spec, "agent")
        self.assertEqual(invalid.code, "tool.invalid_args")
        call = ToolCall("mutate", {"value": 7}, "same-key")
        one = tool_registry.invoke(mutate, call, spec, "turn-a")
        two = tool_registry.invoke(mutate, call, spec, "turn-a")
        self.assertTrue(one.ok and two.ok and two.replayed)
        self.assertEqual(calls, [7])

    def test_usage_context_is_isolated_between_workers(self):
        def read(surface: str):
            return model_router.run_with_usage_context(surface, "test", model_router.get_usage_context)
        expected = ["chat", "agent", "research", "terminal"] * 5
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = list(pool.map(read, expected))
        self.assertEqual([v["surface"] for v in values], expected)

    def test_stream_fallback_never_concatenates_after_partial_output(self):
        class Partial(model_router.BaseLLMClient):
            def complete(self, messages, system=None, max_tokens=2000):
                raise RuntimeError("failed")
            def complete_stream(self, messages, system=None, max_tokens=2000):
                yield "partial"
                raise RuntimeError("stream failed")

        class Backup(model_router.BaseLLMClient):
            def complete(self, messages, system=None, max_tokens=2000):
                return "backup"
            def complete_stream(self, messages, system=None, max_tokens=2000):
                yield "backup"

        stream = model_router.FallbackClient([Partial(), Backup()]).complete_stream([])
        self.assertEqual(next(stream), "partial")
        with self.assertRaises(RuntimeError):
            next(stream)

    def test_compaction_preserves_original_messages(self):
        session = chat_store.create_session("history")
        for i in range(10):
            chat_store.add_message(session["id"], "user" if i % 2 == 0 else "assistant", f"message {i}")
        before = chat_store.get_messages(session["id"], limit=100)
        compacted = chat_store.compact_session(session["id"], "rolling summary", keep=4)
        after = chat_store.get_messages(session["id"], limit=100)
        self.assertIsNotNone(compacted)
        self.assertEqual(len(after), len(before))
        history = chat_store.recent_history(session["id"], limit=6)
        self.assertTrue(history[0]["content"].startswith("[Summary of earlier conversation]"))


if __name__ == "__main__":
    unittest.main()
