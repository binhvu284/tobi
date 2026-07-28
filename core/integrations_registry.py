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


def _reason(exc: BaseException, fallback: str) -> str:
    """Report why a connection test failed instead of guessing on the owner's behalf.

    `except Exception: return "check your connection"` is only true for one of the failures
    it catches. A GitHub App whose installation id points at nothing answers HTTP 404, a
    revoked key answers 401, a repository outside the policy allowlist never leaves the
    process at all -- and every one of those was reported as a network problem, which sends
    the owner to check their wifi while the actual cause sits in the exception being
    discarded. The connectors raise curated messages; the value is in showing them.
    """
    detail = str(exc).strip()
    if not detail:
        return fallback
    return f"{fallback.rstrip('.')} — {type(exc).__name__}: {detail}"[:400]


# ── live tests (read current os.environ) ────────────────────────────────
def _test_github() -> tuple[bool, str]:
    app_fields = ("GITHUB_APP_ID", "GITHUB_APP_INSTALLATION_ID", "GITHUB_APP_PRIVATE_KEY")
    try:
        if all(os.getenv(name) for name in app_fields):
            from core.coding_policy import CodingPolicy
            from core.github_coding import GitHubCodingService
            ok = GitHubCodingService(CodingPolicy.load()).test()
            return (True, "GitHub App installation verified.") if ok else (
                False, "GitHub App verification failed — the installation returned no token.")
        missing = [name for name in app_fields if not os.getenv(name)]
        ok = _intg.GitHubIntegration().test()
        if not ok:
            return False, "GitHub rejected the token — check it hasn't expired and has repo scope."
        if missing and len(missing) < len(app_fields):
            # Partly-filled App config silently falls back to testing the token, which passes
            # and reads as success while Developer push/PR stays unconfigured.
            return True, ("GitHub token valid. Coding App not tested — still missing: "
                          + ", ".join(missing))
        return True, "GitHub token valid."
    except Exception as exc:
        return False, _reason(exc, "Could not reach GitHub.")


def _test_notion() -> tuple[bool, str]:
    try:
        ok = _intg.NotionIntegration().test()
        return (True, "Notion key valid.") if ok else (False, "Notion rejected the key — make sure the integration is shared with your workspace.")
    except Exception as exc:
        return False, _reason(exc, "Could not reach Notion.")


def _test_vercel() -> tuple[bool, str]:
    try:
        ok = _intg.VercelIntegration().test()
        return (True, "Vercel token valid.") if ok else (False, "Vercel rejected the token — create one at vercel.com/account/tokens.")
    except Exception as exc:
        return False, _reason(exc, "Could not reach Vercel.")


def _test_supabase() -> tuple[bool, str]:
    try:
        ok = _intg.SupabaseIntegration().test()
        return (True, "Supabase reachable.") if ok else (False, "Could not reach the Supabase URL with that anon key — check both values.")
    except Exception as exc:
        return False, _reason(exc, "Could not reach Supabase — check the URL and key.")


def _test_llm() -> tuple[bool, str]:
    import requests
    ak = os.getenv("ANTHROPIC_API_KEY")
    if ak:
        try:
            r = requests.get("https://api.anthropic.com/v1/models",
                             headers={"x-api-key": ak, "anthropic-version": "2023-06-01"}, timeout=12)
            return (True, "Anthropic key valid.") if r.status_code == 200 else (False, f"Anthropic rejected the key (HTTP {r.status_code}).")
        except Exception as exc:
            return False, _reason(exc, "Could not reach Anthropic.")
    ork = os.getenv("OPENROUTER_API_KEY")
    if ork:
        try:
            r = requests.get("https://openrouter.ai/api/v1/auth/key",
                             headers={"Authorization": f"Bearer {ork}"}, timeout=12)
            return (True, "OpenRouter key valid.") if r.status_code == 200 else (False, f"OpenRouter rejected the key (HTTP {r.status_code}).")
        except Exception as exc:
            return False, _reason(exc, "Could not reach OpenRouter.")
    return False, "Provide an Anthropic or OpenRouter API key."


def _test_codex() -> tuple[bool, str]:
    """Validate Codex auth (subscription token or API key) with a 1-token ping."""
    import requests

    # Determine auth path: subscription token vs platform API key
    tok = os.getenv("CODEX_ACCESS_TOKEN") or os.getenv("CODEX_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    use_api = False

    if not tok:
        # Try auto-reading from $CODEX_HOME/auth.json or ~/.codex/auth.json
        try:
            import json
            codex_home = os.getenv("CODEX_HOME", "")
            candidates = []
            if codex_home:
                candidates.append(os.path.join(codex_home, "auth.json"))
            candidates.append(os.path.expanduser("~/.codex/auth.json"))
            for path in candidates:
                if os.path.exists(path):
                    with open(path) as f:
                        data = json.load(f)
                    tokens = data.get("tokens")
                    if isinstance(tokens, dict) and tokens.get("access_token"):
                        tok = tokens["access_token"]
                    else:
                        tok = data.get("access_token") or data.get("api_key") or ""
                    if tok:
                        break
        except Exception:
            pass

    if not tok and openai_key:
        tok = openai_key
        use_api = True

    if not tok:
        return False, (
            "No Codex auth found. Either:\n"
            "  • Run `codex login` (auto-reads the token), or\n"
            "  • Paste CODEX_ACCESS_TOKEN, or\n"
            "  • Set OPENAI_API_KEY for API billing."
        )

    # If the key looks like a standard OpenAI key, use the official API endpoint
    if tok.startswith("sk-"):
        use_api = True

    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    model = "gpt-5.6"

    if use_api:
        url = "https://api.openai.com/v1/responses"
    else:
        url = "https://chatgpt.com/backend-api/codex/responses"
        aid = os.getenv("CODEX_CHATGPT_ACCOUNT_ID")
        if aid:
            headers["chatgpt-account-id"] = aid

    try:
        r = requests.post(url, headers=headers, timeout=20,
                          json={"model": model, "input": "ping", "max_output_tokens": 1})
        if r.status_code == 200:
            mode = "API key" if use_api else "ChatGPT subscription"
            return True, f"Codex valid — {mode} auth confirmed."
        if r.status_code in (401, 403):
            hint = "Re-run `codex login`" if not use_api else "Check your API key"
            return False, f"Codex rejected the token (HTTP {r.status_code}). {hint}."
        if r.status_code == 404 and not use_api:
            return False, f"Model '{model}' not found on subscription endpoint — the chatgpt.com backend may have changed. Try using OPENAI_API_KEY instead."
        return False, f"Codex backend returned HTTP {r.status_code}."
    except Exception as exc:
        return False, _reason(exc, "Could not reach the Codex backend.")


def _test_google() -> tuple[bool, str]:
    try:
        g = _intg.GoogleIntegration()
        if not g.is_available():
            return False, "Add your Google OAuth client ID and secret."
        if not g.is_connected():
            return True, "Credentials saved — click 'Connect with Google' to authorize."
        ok = g.test()
        if ok:
            return True, "Google Workspace connected — Drive, Gmail & Calendar ready."
        return False, "Token expired or revoked — try reconnecting."
    except Exception as exc:
        return False, _reason(exc, "Could not reach Google.")


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
    except Exception as exc:
        return False, _reason(exc, "Could not reach Telegram.")


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
        "blurb": "Read repositories with a token, or configure the repository-scoped GitHub App used by Developer workflows.",
        "fields": [
            {"name": "GITHUB_TOKEN", "label": "Personal access token", "type": "api_key",
             "help_url": "https://github.com/settings/tokens"},
            {"name": "GITHUB_APP_ID", "label": "Coding App ID", "type": "text",
             "help_url": "https://github.com/settings/apps"},
            {"name": "GITHUB_APP_INSTALLATION_ID", "label": "Coding App installation ID", "type": "text",
             "help_url": "https://github.com/settings/installations"},
            {"name": "GITHUB_APP_PRIVATE_KEY", "label": "Coding App private key", "type": "password",
             "help_url": "https://github.com/settings/apps"},
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
        "id": "codex", "label": "OpenAI Codex", "category": "tools", "required": False,
        "icon": "codex", "available": True,
        "blurb": "Use GPT-5.6 models (Sol/Terra/Luna) via ChatGPT subscription or OpenAI API key. Run `codex login` to auto-auth, or paste a token / API key.",
        "fields": [
            {"name": "CODEX_ACCESS_TOKEN", "label": "Codex access token (subscription)", "type": "api_key",
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
        "blurb": "API keys for the News page (V1 #9 + V2 #23). Free sources (OpenRouter, HN, LMArena, GDELT, RSS, Reddit) work without keys — add these to light up more. Artificial Analysis and LLM Stats power the V2 Model Strength benchmarks.",
        "fields": [
            {"name": "ARTIFICIALANALYSIS_API_KEY", "label": "Artificial Analysis key (Model Strength)", "type": "api_key", "help_url": "https://artificialanalysis.ai/data-api"},
            {"name": "LLMSTATS_API_KEY", "label": "LLM Stats key (Model Strength)", "type": "api_key", "help_url": "https://llm-stats.com/developer"},
            {"name": "NEWSDATA_API_KEY", "label": "NewsData.io key", "type": "api_key", "help_url": "https://newsdata.io/register"},
            {"name": "GNEWS_API_KEY", "label": "GNews key", "type": "api_key", "help_url": "https://gnews.io/register"},
            {"name": "PRODUCTHUNT_API_TOKEN", "label": "Product Hunt token", "type": "api_key", "help_url": "https://api.producthunt.com/v2/docs"},
            {"name": "TAVILY_API_KEY", "label": "Tavily key", "type": "api_key", "help_url": "https://tavily.com"},
            {"name": "X_BEARER_TOKEN", "label": "X/Twitter bearer (opt-in)", "type": "api_key", "help_url": "https://developer.x.com"},
        ],
        "abilities_unlocked": [],
        "test": None,
    },
    # ── Google Workspace (OAuth2: Drive + Gmail + Calendar) ──
    {
        "id": "google", "label": "Google Workspace", "category": "tools", "required": False,
        "icon": "google", "available": True,
        "blurb": "Drive, Gmail & Calendar via OAuth2. After saving the client ID/secret, click 'Connect with Google' to authorize.",
        "fields": [
            {"name": "GOOGLE_CLIENT_ID", "label": "OAuth client ID", "type": "oauth",
             "help_url": "https://console.cloud.google.com/apis/credentials"},
            {"name": "GOOGLE_CLIENT_SECRET", "label": "OAuth client secret", "type": "oauth",
             "help_url": "https://console.cloud.google.com/apis/credentials"},
        ],
        "abilities_unlocked": ["google_oauth", "gmail_integration", "calendar_integration"],
        "test": _test_google,
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


def test_confirms_read_access(integration_id: str) -> bool:
    """Whether a successful registry test proves the connector can currently read data.

    Google has a two-stage setup: client credentials can be valid before the owner completes
    OAuth. That first stage is successful setup, but it is not verified external read access.
    """
    item = get(integration_id)
    if not item or item.get("test") is None:
        return False
    if integration_id == "google":
        try:
            return _intg.GoogleIntegration().is_connected()
        except Exception:
            return False
    return True
