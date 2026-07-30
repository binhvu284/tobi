"""Regression tests for TOBI's shared Telegram application lifecycle."""
from __future__ import annotations

import asyncio

import pytest

from core import scheduled_jobs


class FakeBot:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def shutdown(self) -> None:
        self.events.append("bot.shutdown")


class FakeUpdater:
    def __init__(self, events: list[str], *, fail_start: bool = False) -> None:
        self.events = events
        self.fail_start = fail_start
        self.running = False

    async def start_polling(self, **_kwargs) -> None:
        self.events.append("updater.start_polling")
        if self.fail_start:
            raise TimeoutError("polling unavailable")
        self.running = True

    async def stop(self) -> None:
        self.events.append("updater.stop")
        self.running = False


class FakeApplication:
    def __init__(
        self,
        events: list[str],
        *,
        fail_initialize: bool = False,
        fail_polling: bool = False,
    ) -> None:
        self.events = events
        self.fail_initialize = fail_initialize
        self.running = False
        self.bot = FakeBot(events)
        self.updater = FakeUpdater(events, fail_start=fail_polling)

    async def initialize(self) -> None:
        self.events.append("app.initialize")
        if self.fail_initialize:
            raise TimeoutError("Telegram timed out")

    async def start(self) -> None:
        self.events.append("app.start")
        self.running = True

    async def stop(self) -> None:
        self.events.append("app.stop")
        self.running = False

    async def shutdown(self) -> None:
        self.events.append("app.shutdown")


def _reset_telegram_state() -> None:
    scheduled_jobs._tg_app = None
    scheduled_jobs._tg_app_lock = asyncio.Lock()


def test_failed_initialization_does_not_poison_singleton(monkeypatch) -> None:
    events: list[str] = []
    applications = iter([
        FakeApplication(events, fail_initialize=True),
        FakeApplication(events),
    ])
    monkeypatch.setattr(scheduled_jobs, "build_app", lambda: next(applications))
    _reset_telegram_state()

    async def scenario() -> None:
        with pytest.raises(TimeoutError, match="timed out"):
            await scheduled_jobs.get_telegram_app()
        assert scheduled_jobs._tg_app is None

        recovered = await scheduled_jobs.get_telegram_app()
        assert recovered is scheduled_jobs._tg_app
        await scheduled_jobs.shutdown_telegram_app()

    asyncio.run(scenario())

    assert events == [
        "app.initialize",
        "bot.shutdown",
        "app.initialize",
        "app.shutdown",
    ]


def test_polling_uses_required_order_and_shutdown_is_idempotent(monkeypatch) -> None:
    events: list[str] = []
    application = FakeApplication(events)
    monkeypatch.setattr(scheduled_jobs, "build_app", lambda: application)
    _reset_telegram_state()

    async def scenario() -> None:
        first = await scheduled_jobs.start_telegram_polling()
        second = await scheduled_jobs.start_telegram_polling()
        assert first is second
        await scheduled_jobs.shutdown_telegram_app()
        await scheduled_jobs.shutdown_telegram_app()

    asyncio.run(scenario())

    assert events == [
        "app.initialize",
        "updater.start_polling",
        "app.start",
        "updater.stop",
        "app.stop",
        "app.shutdown",
    ]


def test_polling_failure_clears_singleton_for_retry(monkeypatch) -> None:
    events: list[str] = []
    applications = iter([
        FakeApplication(events, fail_polling=True),
        FakeApplication(events),
    ])
    monkeypatch.setattr(scheduled_jobs, "build_app", lambda: next(applications))
    _reset_telegram_state()

    async def scenario() -> None:
        with pytest.raises(TimeoutError, match="polling unavailable"):
            await scheduled_jobs.start_telegram_polling()
        assert scheduled_jobs._tg_app is None

        recovered = await scheduled_jobs.start_telegram_polling()
        assert recovered.running
        await scheduled_jobs.shutdown_telegram_app()

    asyncio.run(scenario())

    assert events == [
        "app.initialize",
        "updater.start_polling",
        "app.shutdown",
        "app.initialize",
        "updater.start_polling",
        "app.start",
        "updater.stop",
        "app.stop",
        "app.shutdown",
    ]
