"""Guard the rotating Codex login from stale vault credentials.

Mission Control injects vault secrets into the server environment. A copied
CODEX_ACCESS_TOKEN can therefore shadow the newer token maintained by `codex
login`, even though both credentials represent the same ChatGPT account.
"""
from __future__ import annotations

import base64
import json
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.llm_clients.codex import CodexClient


def _jwt(expiry: int, marker: str) -> str:
    def _part(payload: dict) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{_part({'alg': 'none'})}.{_part({'exp': expiry, 'marker': marker})}.sig"


class _Event:
    def __init__(self, type_: str, **values) -> None:
        self.type = type_
        for key, value in values.items():
            setattr(self, key, value)


class _Usage:
    input_tokens = 1
    output_tokens = 1


class _Response:
    usage = _Usage()
    status = "completed"


class _AuthenticationError(Exception):
    status_code = 401


class _FakeOpenAI:
    stale_token = ""
    created_with: list[str] = []

    def __init__(self, *, api_key: str, **_kwargs) -> None:
        self.api_key = api_key
        self.created_with.append(api_key)
        self.responses = self

    def create(self, **_kwargs):
        if self.api_key == self.stale_token:
            raise _AuthenticationError("expired")
        return [
            _Event("response.output_text.delta", delta="ok"),
            _Event("response.completed", response=_Response()),
        ]


class _PartialOpenAI(_FakeOpenAI):
    def create(self, **_kwargs):
        def _events():
            yield _Event("response.output_text.delta", delta="partial")
            raise _AuthenticationError("expired after output")

        return _events()


class CodexAuthFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeOpenAI.created_with = []

    def _openai_module(self):
        return patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=_FakeOpenAI)})

    def test_newer_codex_login_wins_over_stale_configured_token(self) -> None:
        now = int(time.time())
        stale = _jwt(now + 60, "vault")
        fresh = _jwt(now + 3600, "login")
        _FakeOpenAI.stale_token = stale

        with self._openai_module(), \
                patch.object(CodexClient, "_read_codex_auth", return_value=fresh), \
                patch.object(CodexClient, "_read_codex_account_id", return_value="login-account"):
            client = CodexClient("gpt-5.6-sol", api_key=stale)

        self.assertEqual(client.auth_source, "codex_login")
        self.assertEqual(_FakeOpenAI.created_with, [fresh])
        self.assertEqual(client.account_id, "login-account")

    def test_newer_configured_token_is_not_replaced(self) -> None:
        now = int(time.time())
        configured = _jwt(now + 7200, "vault")
        older_login = _jwt(now + 3600, "login")
        _FakeOpenAI.stale_token = ""

        with self._openai_module(), \
                patch.object(CodexClient, "_read_codex_auth", return_value=older_login):
            client = CodexClient("gpt-5.6-sol", api_key=configured)

        self.assertEqual(client.auth_source, "configured")
        self.assertEqual(_FakeOpenAI.created_with, [configured])

    def test_401_refreshes_from_codex_login_once(self) -> None:
        now = int(time.time())
        stale = _jwt(now + 3600, "initial")
        fresh = _jwt(now + 7200, "rotated")
        _FakeOpenAI.stale_token = stale
        reads = iter((stale, fresh))

        with self._openai_module(), \
                patch.object(CodexClient, "_read_codex_auth", side_effect=lambda: next(reads)), \
                patch.object(CodexClient, "_read_codex_account_id", return_value="login-account"), \
                patch.object(CodexClient, "_log_failure", return_value=None), \
                patch.object(CodexClient, "_log_usage", return_value=None):
            client = CodexClient("gpt-5.6-sol", api_key=stale)
            result = client.complete([{"role": "user", "content": "reply ok"}], max_tokens=8)

        self.assertEqual(result, "ok")
        self.assertEqual(client.auth_source, "codex_login_retry")
        self.assertEqual(_FakeOpenAI.created_with, [stale, fresh])

    def test_partial_stream_is_never_replaced_after_authentication_failure(self) -> None:
        now = int(time.time())
        token = _jwt(now + 3600, "stream")

        with patch.dict(
            sys.modules, {"openai": types.SimpleNamespace(OpenAI=_PartialOpenAI)}
        ), patch.object(CodexClient, "_read_codex_auth", return_value=token):
            client = CodexClient("gpt-5.6-sol", api_key=token)
            stream = client.complete_stream(
                [{"role": "user", "content": "reply"}], max_tokens=8
            )
            self.assertEqual(next(stream), "partial")
            with self.assertRaises(_AuthenticationError):
                next(stream)

        self.assertEqual(client.auth_source, "configured")


if __name__ == "__main__":
    unittest.main()
