"""Integration registry — Tobi "Genesis Complete".

A single source of truth describing every configurable integration: the secret
fields it needs, the Genesis abilities it unlocks, whether it's required, and how
to live-test it. Tests reuse the existing connectors in ``core/integrations.py``
(which read their keys from ``os.environ``), plus lightweight LLM/Telegram pings.

The vault injects candidate keys into ``os.environ`` before a test runs, so these
functions just construct a fresh connector and call its ``.test()``.
"""
from __future__ import annotations

import os
from typing import Callable

from core import integrations as _intg

TestFn = Callable[[], "tuple[bool, str]"]


# ── live tests (read current os.environ) ────────────────────────────────
def _test_github() -> tuple[bool, str]:
    try:
        ok = _intg.GitHubIntegration().test()
        return (True, "GitHub token valid.") if ok else (False, "GitHub rejected the token — check it hasn't expired and has repo scope.")
    except Exception:
        return False, "Could not reach GitHub — check your connection."


def _test_notion() -> tuple[bool, str]:
    try:
        ok = _intg.NotionIntegration().test()
        return (True, "Notion key valid.") if ok else (False, "Notion rejected the key — make sure the integration is shared with your workspace.")
    except Exception:
        return False, "Could not reach Notion — check your connection."


def _test_vercel() -> tuple[bool, str]:
    try:
        ok = _intg.VercelIntegration().test()
        return (True, "Vercel token valid.") if ok else (False, "Vercel rejected the token — create one at vercel.com/account/tokens.")
    except Exception:
        return False, "Could not reach Vercel — check your connection."


def _test_supabase() -> tuple[bool, str]:
    try:
        ok = _intg.SupabaseIntegration().test()
        return (True, "Supabase reachable.") if ok else (False, "Could not reach the Supabase URL with that anon key — check both values.")
    except Exception:
        return False, "Could not reach Supabase — check the URL and key."


def _test_llm() -> tuple[bool, str]:
    import requests
    ak = os.getenv("ANTHROPIC_API_KEY")
    if ak:
        try:
            r = requests.get("https://api.anthropic.com/v1/models",
                             headers={"x-api-key": ak, "anthropic-version": "2023-06-01"}, timeout=12)
            return (True, "Anthropic key valid.") if r.status_code == 200 else (False, f"Anthropic rejected the key (HTTP {r.status_code}).")
        except Exception:
            return False, "Could not reach Anthropic — check your connection."
    ork = os.getenv("OPENROUTER_API_KEY")
    if ork:
        try:
            r = requests.get("https://openrouter.ai/api/v1/auth/key",
                             headers={"Authorization": f"Bearer {ork}"}, timeout=12)
            return (True, "OpenRouter key valid.") if r.status_code == 200 else (False, f"OpenRouter rejected the key (HTTP {r.status_code}).")
        except Exception:
            return False, "Could not reach OpenRouter — check your connection."
    return False, "Provide an Anthropic or OpenRouter API key."


def _test_codex() -> tuple[bool, str]:
    """Validate the Codex access_token by issuing a 1-token request against the
    chatgpt.com backend Responses API (uses Plus subscription quota)."""
    import requests
    tok = os.getenv("CODEX_ACCESS_TOKEN")
    if not tok:
        return False, "Paste the access_token from ~/.codex/auth.json (run `codex login` first)."
    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    aid = os.getenv("CODEX_CHATGPT_ACCOUNT_ID")
    if aid:
        headers["chatgpt-account-id"] = aid
    try:
        r = requests.post(
            "https://chatgpt.com/backend-api/codex/responses",
            headers=headers, timeout=20,
            json={"model": "gpt-5-codex", "input": "ping", "max_output_tokens": 1},
        )
        if r.status_code == 200:
            return True, "Codex token valid — Plus subscription linked."
        if r.status_code in (401, 403):
            return False, f"Codex rejected the token (HTTP {r.status_code}) — re-run `codex login` and refresh it."
        return False, f"Codex backend returned HTTP {r.status_code}."
    except Exception:
        return False, "Could not reach the Codex backend — check your connection."


def _test_telegram() -> tuple[bool, str]:
    import requests
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    if not tok:
        return False, "Provide a bot token from @BotFather."
    try:
        r = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=12)
        data = r.json() if r.status_code == 200 else {}
        if data.get("ok"):
            return True, f"Connected as @{data.get('result', {}).get('username', 'bot')}."
        return False, "Telegram rejected the token — double-check it from @BotFather."
    except Exception:
        return False, "Could not reach Telegram — check your connection."


# ── registry ────────────────────────────────────────────────────────────
# category: core (required prereqs) | tools | coming_soon | custom
REGISTRY: list[dict] = [
    {
        "id": "llm", "label": "LLM Provider", "category": "core", "required": True,
        "icon": "brain", "available": True,
        "blurb": "Anthropic or OpenRouter — the brain behind every response, the coding agent, cron, and reports.",
        "fields": [
            {"name": "ANTHROPIC_API_KEY", "label": "Anthropic API key", "type": "api_key",
             "help_url": "https://console.anthropic.com/settings/keys", "optional_group": "llm"},
            {"name": "OPENROUTER_API_KEY", "label": "OpenRouter API key", "type": "api_key",
             "help_url": "https://openrouter.ai/keys", "optional_group": "llm"},
        ],
        "abilities_unlocked": ["coding_agent", "cron_scheduler", "proactive_reports"],
        "test": _test_llm,
    },
    {
        "id": "telegram", "label": "Telegram Bot", "category": "core", "required": True,
        "icon": "send", "available": True,
        "blurb": "Your always-on 24/7 interface to Tobi. Also gates the cron scheduler and proactive reports.",
        "fields": [
            {"name": "TELEGRAM_BOT_TOKEN", "label": "Bot token", "type": "api_key",
             "help_url": "https://t.me/BotFather"},
        ],
        "abilities_unlocked": ["telegram_bot", "cron_scheduler", "proactive_reports"],
        "test": _test_telegram,
    },
    {
        "id": "github", "label": "GitHub", "category": "tools", "required": False,
        "icon": "github", "available": True,
        "blurb": "Read repos, manage issues and PRs via the GitHub REST API.",
        "fields": [
            {"name": "GITHUB_TOKEN", "label": "Personal access token", "type": "api_key",
             "help_url": "https://github.com/settings/tokens"},
        ],
        "abilities_unlocked": ["github_integration"],
        "test": _test_github,
    },
    {
        "id": "notion", "label": "Notion", "category": "tools", "required": False,
        "icon": "notion", "available": True,
        "blurb": "Read and write Notion pages and databases.",
        "fields": [
            {"name": "NOTION_API_KEY", "label": "Internal integration secret", "type": "api_key",
             "help_url": "https://www.notion.so/my-integrations"},
        ],
        "abilities_unlocked": ["notion_integration"],
        "test": _test_notion,
    },
    {
        "id": "vercel", "label": "Vercel", "category": "tools", "required": False,
        "icon": "triangle", "available": True,
        "blurb": "Deploy projects and query deployment status.",
        "fields": [
            {"name": "VERCEL_TOKEN", "label": "Access token", "type": "api_key",
             "help_url": "https://vercel.com/account/tokens"},
        ],
        "abilities_unlocked": ["vercel_integration"],
        "test": _test_vercel,
    },
    {
        "id": "supabase", "label": "Supabase", "category": "tools", "required": False,
        "icon": "database", "available": True,
        "blurb": "Run SQL/REST queries against a Supabase project.",
        "fields": [
            {"name": "SUPABASE_URL", "label": "Project URL", "type": "url",
             "help_url": "https://supabase.com/dashboard/project/_/settings/api"},
            {"name": "SUPABASE_ANON_KEY", "label": "anon public key", "type": "api_key",
             "help_url": "https://supabase.com/dashboard/project/_/settings/api"},
        ],
        "abilities_unlocked": ["supabase_integration"],
        "test": _test_supabase,
    },
    {
        "id": "codex", "label": "OpenAI Codex (ChatGPT Plus)", "category": "tools", "required": False,
        "icon": "codex", "available": True,
        "blurb": "Use your ChatGPT Plus subscription's Codex quota. Run `codex login` locally, then paste the access_token from ~/.codex/auth.json.",
        "fields": [
            {"name": "CODEX_ACCESS_TOKEN", "label": "Codex access token", "type": "api_key",
             "help_url": "https://chatgpt.com/codex"},
            {"name": "CODEX_CHATGPT_ACCOUNT_ID", "label": "ChatGPT account ID (optional)", "type": "api_key",
             "help_url": "https://chatgpt.com/codex"},
        ],
        "abilities_unlocked": [],
        "test": _test_codex,
    },
    {
        "id": "explore", "label": "Explore (News) sources", "category": "tools", "required": False,
        "icon": "newspaper", "available": True,
        "blurb": "API keys for the Explore → News page (#9). Free sources (OpenRouter, HN, GDELT, RSS, Reddit) work without keys — add these to light up more.",
        "fields": [
            {"name": "NEWSDATA_API_KEY", "label": "NewsData.io key", "type": "api_key", "help_url": "https://newsdata.io/register"},
            {"name": "GNEWS_API_KEY", "label": "GNews key", "type": "api_key", "help_url": "https://gnews.io/register"},
            {"name": "PRODUCTHUNT_API_TOKEN", "label": "Product Hunt token", "type": "api_key", "help_url": "https://api.producthunt.com/v2/docs"},
            {"name": "TAVILY_API_KEY", "label": "Tavily key", "type": "api_key", "help_url": "https://tavily.com"},
            {"name": "X_BEARER_TOKEN", "label": "X/Twitter bearer (opt-in)", "type": "api_key", "help_url": "https://developer.x.com"},
        ],
        "abilities_unlocked": [],
        "test": None,
    },
    # ── forward-looking placeholders (configurable now, activated in Awakening) ──
    {
        "id": "google", "label": "Google Workspace", "category": "coming_soon", "required": False,
        "icon": "google", "available": False, "coming_in": "Awakening",
        "blurb": "Drive, Docs, Sheets & Calendar via OAuth. Store the client id/secret now; OAuth lands in Awakening.",
        "fields": [
            {"name": "GOOGLE_CLIENT_ID", "label": "OAuth client ID", "type": "oauth", "help_url": "https://console.cloud.google.com/apis/credentials"},
            {"name": "GOOGLE_CLIENT_SECRET", "label": "OAuth client secret", "type": "oauth", "help_url": "https://console.cloud.google.com/apis/credentials"},
        ],
        "abilities_unlocked": ["google_oauth"],
        "test": None,
    },
    {
        "id": "gmail", "label": "Gmail", "category": "coming_soon", "required": False,
        "icon": "mail", "available": False, "coming_in": "Awakening",
        "blurb": "Read inbox, summarize threads, draft replies. Arrives in Awakening.",
        "fields": [
            {"name": "GMAIL_CLIENT_ID", "label": "OAuth client ID", "type": "oauth", "help_url": "https://console.cloud.google.com/apis/credentials"},
            {"name": "GMAIL_CLIENT_SECRET", "label": "OAuth client secret", "type": "oauth", "help_url": "https://console.cloud.google.com/apis/credentials"},
        ],
        "abilities_unlocked": ["gmail_integration"],
        "test": None,
    },
    {
        "id": "stripe", "label": "Stripe", "category": "coming_soon", "required": False,
        "icon": "credit-card", "available": False, "coming_in": "Awakening",
        "blurb": "Payment events + webhooks for the Operator tier. Store the keys now.",
        "fields": [
            {"name": "STRIPE_SECRET_KEY", "label": "Secret key", "type": "api_key", "help_url": "https://dashboard.stripe.com/apikeys"},
            {"name": "STRIPE_WEBHOOK_SECRET", "label": "Webhook signing secret", "type": "webhook", "help_url": "https://dashboard.stripe.com/webhooks"},
        ],
        "abilities_unlocked": [],
        "test": None,
    },
]

_BY_ID = {item["id"]: item for item in REGISTRY}


def get(integration_id: str) -> dict | None:
    return _BY_ID.get(integration_id)


def all_field_names() -> list[str]:
    names: list[str] = []
    for item in REGISTRY:
        for f in item["fields"]:
            names.append(f["name"])
    return names


def test_integration(integration_id: str) -> tuple[bool, str]:
    """Run an integration's live test against the current os.environ."""
    item = get(integration_id)
    if not item:
        return False, "Unknown integration."
    fn: TestFn | None = item.get("test")
    if fn is None:
        return True, "Saved (no live test for this integration)."
    return fn()
