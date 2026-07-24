"""Ability / tier detection for Evolution + Awakening (moved from api/dashboard.py).

Pure, dependency-light logic (no FastAPI, no dashboard globals) so BOTH the API
layer and core.conductor can import it directly - this removes the old core->api
backward dependency (conductor previously did `from api import dashboard`). The
symbols keep their leading-underscore names + verbatim bodies; this is a move, not
a rewrite. See docs/REFACTORING_PLAN.md.
"""
from __future__ import annotations

import os
import sqlite3  # noqa: F401 - used in the moved type hints
from pathlib import Path


_TIER_DEFINITIONS: list[dict] = [
    {
        "id": 0, "roman": "0", "name": "GENESIS", "color_key": "gray",
        "tagline": "Tobi exists. It talks back. That's about it.",
        "pillars": {
            "understand": [
                {"id": "soul_md", "name": "Static persona file (SOUL.md)",
                 "description": "Hand-written file defining Tobi's personality and rules. Works, but static — you wrote it yourself.", "how_to_unlock": None, "effort": "done"},
                {"id": "conversation_history", "name": "Conversation history (last 50 msgs)",
                 "description": "50-message rolling window per chat persisted in SQLite. Tobi remembers the current conversation.", "how_to_unlock": None, "effort": "done"},
                {"id": "task_classifier", "name": "Regex task classifier",
                 "description": "Routes messages to SMALLTALK/CODING/RESEARCH/STATUS/EXECUTION via regex — no LLM call needed. Fast and deterministic.", "how_to_unlock": None, "effort": "done"},
                {"id": "lessons_store", "name": "Lessons store (self-reflection DB)",
                 "description": "After cycles, Tobi logs success/failure/insight/warning entries to SQLite. The beginning of institutional memory.", "how_to_unlock": "The store is built and wired — it just needs its first entry. Click “Reflect now” below to run a self-reflection and write lesson #1, or wait for the Sunday 20:00 weekly reflection. Any logged lesson (cycle outcome, /note, coaching) also activates it.", "effort": "done"},
            ],
            "control": [
                {"id": "coding_agent", "name": "Sandboxed coding agent",
                 "description": "Claude tool-use loop with 4 tools: read_file, write_file, run_bash, list_files. Sandboxed to project dir with 30s timeout.", "how_to_unlock": None, "effort": "done"},
                {"id": "github_integration", "name": "GitHub integration",
                 "description": "API-key gated. Read repos, create issues, manage PRs via GitHub REST API.", "how_to_unlock": None, "effort": "done"},
                {"id": "notion_integration", "name": "Notion integration",
                 "description": "API-key gated. Read and write Notion pages and databases.", "how_to_unlock": None, "effort": "done"},
                {"id": "vercel_integration", "name": "Vercel integration",
                 "description": "API-key gated. Deploy projects and query deployment status.", "how_to_unlock": None, "effort": "done"},
                {"id": "supabase_integration", "name": "Supabase integration",
                 "description": "API-key gated. Run SQL queries against a Supabase database.", "how_to_unlock": None, "effort": "done"},
            ],
            "presence": [
                {"id": "telegram_bot", "name": "Telegram bot (24/7 reachable)",
                 "description": "Always-listening bot. Your main interface to Tobi — text commands, inline buttons, coding agent access.", "how_to_unlock": None, "effort": "done"},
                {"id": "cron_scheduler", "name": "Cron scheduler",
                 "description": "Scheduled jobs: daily 08:00 report, 6h execution cycle, weekly research, monthly CEO review.", "how_to_unlock": None, "effort": "done"},
                {"id": "proactive_reports", "name": "Proactive daily reports",
                 "description": "Tobi pushes status updates to Telegram without being asked — project summaries, revenue, human todos.", "how_to_unlock": None, "effort": "done"},
            ],
        },
    },
    {
        "id": 1, "roman": "I", "name": "AWAKENING", "color_key": "bronze",
        "tagline": "Tobi starts remembering who you are and acting on the real world.",
        "pillars": {
            "understand": [
                {"id": "user_profile_table", "name": "Structured auto-updating user profile",
                 "description": "A real DB table tracking preferences, active projects, habits, relationships — auto-updated from every interaction. No more hand-writing SOUL.md.",
                 "how_to_unlock": "Design user_profile schema. Add entity extraction to handle_chat() to write preferences/projects/people as you mention them.", "effort": "1 week"},
                {"id": "memory_first_retrieval", "name": "Memory-first retrieval in all tasks",
                 "description": "Every task starts by consulting your profile first. The Memory-First Rule in SOUL.md made real in code, not just a text directive.",
                 "how_to_unlock": "Wire profile_context() into build_system_prompt() and every task handler before the LLM call.", "effort": "1 week"},
                {"id": "entity_extraction", "name": "Entity extraction from conversations",
                 "description": "Auto-extract people, projects, preferences, and decisions from your chats and persist them to the user profile.",
                 "how_to_unlock": "Add a background async call after each message to extract entities via a lightweight LLM prompt and upsert to the profile table.", "effort": "1 week"},
            ],
            "control": [
                {"id": "full_filesystem", "name": "Full filesystem access (no sandbox)",
                 "description": "Remove PROJECT_DIR lock. Tobi reads/writes anywhere on the machine with risk-tiered confirmation for destructive actions.",
                 "how_to_unlock": "Replace PROJECT_DIR sandbox with a risk-tiered permission check. Reads are free; writes outside project prompt once; deletes always confirm.", "effort": "3 days"},
                {"id": "tiered_permissions", "name": "Tiered permission model",
                 "description": "SOUL.md already defines 3 tiers: low (auto-execute), medium (act+report), high (propose+wait). Replace _BLOCKED_CMDS denylist with this.",
                 "how_to_unlock": "Implement classify_risk(command) returning low/medium/high. Replace denylist check in _execute_tool() with risk-gated routing.", "effort": "1 week"},
                {"id": "google_oauth", "name": "Google OAuth integration",
                 "description": "OAuth2 flow for Drive, Gmail & Calendar. Read files, search inbox, check calendar — all through one Google Cloud OAuth client.",
                 "how_to_unlock": None, "effort": "done"},
            ],
            "presence": [
                {"id": "webhook_triggers", "name": "Webhook + event-driven triggers",
                 "description": "Move beyond cron. Add FastAPI webhook endpoints for Stripe events, GitHub, email — Tobi acts when something happens, not just at 8am.",
                 "how_to_unlock": "Add POST /webhooks/{source} endpoints. Map event types to Tobi actions. Wire to Telegram notification on receipt.", "effort": "1 week"},
                {"id": "gmail_integration", "name": "Gmail read",
                 "description": "Tobi reads your inbox, summarizes threads, and surfaces important emails.",
                 "how_to_unlock": None, "effort": "done"},
                {"id": "voice_messages", "name": "Telegram voice messages (Whisper)",
                 "description": "Send a voice note to Tobi. It transcribes via Whisper and responds. Whisper is free and runs locally on CPU.",
                 "how_to_unlock": "Add voice message handler to telegram_bot.py. Download .ogg, convert to wav, run whisper.transcribe(), feed to handle_chat().", "effort": "3 days"},
            ],
        },
    },
    {
        "id": 2, "roman": "II", "name": "AGENT", "color_key": "gold",
        "tagline": "Tobi does real things on the internet. Not plans — actions.",
        "pillars": {
            "understand": [
                {"id": "semantic_memory", "name": "Semantic memory search",
                 "description": "Vector embeddings over all past conversations and lessons. 'What did I decide about X last month?' becomes a real query.",
                 "how_to_unlock": "Integrate SQLite-vec or ChromaDB. Embed messages on save. Add retrieve_similar(query) to the context pipeline.", "effort": "1 week"},
                {"id": "relationship_tracking", "name": "Relationship tracking (contacts DB)",
                 "description": "Tobi knows the people in your life: name, role, last contact, context. Never asks 'who is X?' again.",
                 "how_to_unlock": "Add a people table. Extract person mentions in entity extraction. Link to conversation context.", "effort": "1 week"},
                {"id": "profile_soul_sync", "name": "Profile auto-syncs to SOUL.md",
                 "description": "Tobi maintains SOUL.md itself based on what it learns about you — preferences, priorities, working style. Not hand-authored.",
                 "how_to_unlock": "Add weekly job that reads user profile and rewrites SOUL.md relevant sections using an LLM.", "effort": "1 week"},
            ],
            "control": [
                {"id": "browser_automation", "name": "Browser automation (Playwright)",
                 "description": "The single largest capability unlock. Tobi navigates websites, fills forms, publishes content, scrapes data. Any website is a tool.",
                 "how_to_unlock": "pip install playwright. Add browser_navigate, browser_click, browser_screenshot, browser_fill tools to the coding agent.", "effort": "1 week"},
                {"id": "web_publishing", "name": "Web content publishing",
                 "description": "Tobi publishes an article to Medium, Substack, or a blog — not just writes the draft, but actually posts it.",
                 "how_to_unlock": "Build platform-specific publishing modules using Playwright + platform APIs. Medium and Substack have unofficial APIs.", "effort": "1 week"},
                {"id": "shell_full_access", "name": "Controlled full-machine shell",
                 "description": "Run any terminal command on the full machine (not just project dir), with risk-gating and timeout.",
                 "how_to_unlock": "Build on the tiered permission model (Tier 1). run_bash() gets full machine CWD and no artificial path restriction.", "effort": "3 days"},
            ],
            "presence": [
                {"id": "calendar_integration", "name": "Google Calendar integration",
                 "description": "Tobi knows your schedule. Lists upcoming events, checks availability, preps briefings before meetings.",
                 "how_to_unlock": None, "effort": "done"},
                {"id": "market_monitoring", "name": "Proactive news + market monitoring",
                 "description": "Tobi watches crypto prices, competitor sites, RSS feeds, and reaches out when something relevant happens.",
                 "how_to_unlock": "Add background polling tasks (crypto APIs, RSS, Tavily). Diff against previous state. Telegram alert on significant change.", "effort": "1 week"},
                {"id": "multi_channel", "name": "Multi-channel (Telegram + email)",
                 "description": "Tobi reaches you via email as well as Telegram, routing urgency-appropriate messages to the right channel.",
                 "how_to_unlock": "Add send_email() via Gmail. Add channel preference to SOUL.md: urgent → Telegram, daily → email.", "effort": "3 days"},
            ],
        },
    },
    {
        "id": 3, "roman": "III", "name": "OPERATOR", "color_key": "green",
        "tagline": "Tobi makes money. Not plans about money — actual money.",
        "pillars": {
            "understand": [
                {"id": "episodic_memory", "name": "Long-term episodic memory",
                 "description": "Months of history, semantically searchable. You never re-explain your situation to Tobi.",
                 "how_to_unlock": "Scale up semantic memory (Tier 2) to full history. Add episodic indexing with time decay. Integrate into every task context.", "effort": "1 month"},
                {"id": "habit_recognition", "name": "Habit and pattern recognition",
                 "description": "Tobi notices when you work best, how you like information formatted, what kinds of tasks you delegate.",
                 "how_to_unlock": "Track interaction timestamps, message formats, task acceptance patterns. Weekly analysis job updates habit profile.", "effort": "1 month"},
                {"id": "cross_session_recall", "name": "Zero re-explanation needed",
                 "description": "Anything you've told Tobi is recalled and applied. You mention a person once — Tobi knows them forever.",
                 "how_to_unlock": "Combination of entity extraction (T1) + semantic memory (T2) + episodic memory, fully wired into every message context.", "effort": "1 week"},
            ],
            "control": [
                {"id": "revenue_pipeline", "name": "End-to-end revenue pipeline",
                 "description": "At least one working pipeline from idea to sale: create a product, publish it, and track real revenue — fully automated.",
                 "how_to_unlock": "Pick one revenue channel (e.g. Gumroad). Wire create → upload → publish → track using their API + Playwright for gaps.", "effort": "1 month"},
                {"id": "stripe_gumroad_webhooks", "name": "Stripe + Gumroad live webhooks",
                 "description": "Revenue events hit the DB in real-time. Every sale triggers instant Telegram notification with running totals.",
                 "how_to_unlock": "Add POST /webhooks/stripe and /webhooks/gumroad. Parse sale events, write to revenue table, Telegram alert.", "effort": "1 week"},
                {"id": "social_automation", "name": "Automated social media publishing",
                 "description": "Tobi posts to X/Twitter, LinkedIn, Reddit on your behalf. Content created, scheduled, published autonomously.",
                 "how_to_unlock": "Twitter API v2, LinkedIn unofficial API or Playwright, Reddit API. Add publish_social(platform, content) to tool set.", "effort": "1 month"},
            ],
            "presence": [
                {"id": "proactive_initiative", "name": "Proactive initiative (notices + acts)",
                 "description": "Tobi reaches out when it notices something worth your attention — not cron-triggered, genuinely event-driven with judgment.",
                 "how_to_unlock": "Add observation loop monitoring: revenue trends, project stalls, opportunities. Tobi messages you when a threshold is crossed.", "effort": "1 month"},
                {"id": "revenue_alerts", "name": "Real-time revenue alerts",
                 "description": "Every sale triggers instant Telegram notification. Running monthly total. Revenue milestones celebrated.",
                 "how_to_unlock": "Follows from stripe_gumroad_webhooks + Telegram push. Add milestone detection ($1 first sale, $100, $500, $1000).", "effort": "1 week"},
                {"id": "smart_briefings", "name": "Smart context-aware daily briefings",
                 "description": "Morning briefing synthesizes revenue, project status, calendar, news. Context-aware narrative, not a template.",
                 "how_to_unlock": "Upgrade job_daily_report() to pull all sources + use LLM to synthesize a coherent narrative instead of a template.", "effort": "1 week"},
            ],
        },
    },
    {
        "id": 4, "roman": "IV", "name": "EXECUTIVE", "color_key": "neon_blue",
        "tagline": "Tobi runs parallel agents and starts controlling your desktop.",
        "pillars": {
            "understand": [
                {"id": "strategy_self_update", "name": "Self-updating strategy from outcomes",
                 "description": "Tobi reviews its own performance results and updates its operating strategy without the monthly CEO review prompt.",
                 "how_to_unlock": "Add outcome-tracking to every task. Weekly strategy diff: compare planned vs actual. LLM synthesizes updated SOUL.md strategy section.", "effort": "1 month"},
                {"id": "cross_project_synthesis", "name": "Cross-project pattern synthesis",
                 "description": "'Your last 3 content projects failed at week 2 due to distribution.' Tobi sees the meta-level patterns you miss.",
                 "how_to_unlock": "Add cross_project_analysis() job. Compare project histories. Extract recurring patterns. Surface in weekly briefing.", "effort": "1 month"},
                {"id": "auto_learns_feedback", "name": "Auto-learns from every outcome",
                 "description": "Task done → lesson auto-generated. Revenue experiment failed → strategy auto-updated. No manual reflection prompts needed.",
                 "how_to_unlock": "Add outcome hooks to project_executor.py: on task_done call generate_lesson(). On revenue_event call update_strategy().", "effort": "1 month"},
            ],
            "control": [
                {"id": "desktop_automation", "name": "Desktop GUI automation (vision + click)",
                 "description": "Screenshot → Claude vision → PyAutoGUI. Tobi sees your screen and clicks, types, automates any desktop app.",
                 "how_to_unlock": "pip install pyautogui mss. Add take_screenshot, find_on_screen, click_at, type_text tools. Claude vision interprets screenshots.", "effort": "1 month"},
                {"id": "multi_agent_parallel", "name": "Multi-agent parallelism (3 concurrent)",
                 "description": "Complex tasks spawn 3 sub-agents working in parallel. Research 5 niches = 3x faster.",
                 "how_to_unlock": "Implement async task queue with worker pool. Add delegate_to_agent(task, context) tool. Wire into research_engine and project_executor.", "effort": "1 month"},
                {"id": "local_pc_deployment", "name": "Local PC deployment",
                 "description": "Tobi runs on your actual machine — not a Codespace. Startup daemon, system tray, true desktop access.",
                 "how_to_unlock": "Write local launcher. Handle autostart (launchd on Mac, systemd on Linux). Move DB to user home dir.", "effort": "1 month"},
            ],
            "presence": [
                {"id": "wake_word", "name": "Wake word interface ('Hey Tobi')",
                 "description": "Wake word detection + Whisper STT + TTS. Hands-free. Talk to Tobi while working. Requires local PC deployment.",
                 "how_to_unlock": "pvporcupine for wake word. Whisper for STT. Coqui TTS. Requires local_pc_deployment (also Tier 4).", "effort": "1 month"},
                {"id": "system_tray", "name": "System tray + desktop notifications",
                 "description": "Tobi lives in your taskbar. Status indicator, quick-access menu, native desktop notifications.",
                 "how_to_unlock": "pystray for system tray. plyer for OS notifications. Requires local_pc_deployment.", "effort": "1 month"},
                {"id": "voice_output", "name": "Voice output (TTS responses)",
                 "description": "Tobi speaks back. Coqui TTS is free and local. ElevenLabs for higher quality. Toggle on/off.",
                 "how_to_unlock": "pip install TTS (Coqui). Add speak(text). Toggle via /voice command or system tray.", "effort": "1 week"},
            ],
        },
    },
    {
        "id": 5, "roman": "V", "name": "SENTINEL", "color_key": "gold_white",
        "tagline": "Tobi watches everything and acts before you ask.",
        "pillars": {
            "understand": [
                {"id": "predictive_assistance", "name": "Predictive assistance",
                 "description": "Tobi anticipates what you need before you ask. Pre-loads context before meetings, queues research before calls.",
                 "how_to_unlock": "Build prediction model from calendar + past behavior. Pre-fetch relevant context 30min before scheduled events.", "effort": "1 month"},
                {"id": "behavioral_modeling", "name": "Deep behavioral pattern modeling",
                 "description": "Comprehensive model of work patterns, decision history, risk appetite, communication style, cognitive preferences.",
                 "how_to_unlock": "Aggregate 3+ months interaction data. Statistical profile. Feed into all LLM context as 'owner behavioral model'.", "effort": "1 month"},
                {"id": "autonomous_research", "name": "Autonomous proactive research",
                 "description": "Tobi researches topics relevant to your active projects without being asked. Surfaces insights weekly.",
                 "how_to_unlock": "Add research_daemon() running nightly. For each active project, run targeted Tavily research. Weekly summary to Telegram.", "effort": "1 month"},
            ],
            "control": [
                {"id": "full_app_control", "name": "Full desktop application control",
                 "description": "Tobi operates any desktop app: IDE, browser, Slack, email client, spreadsheets — via vision + automation.",
                 "how_to_unlock": "Extend desktop automation (Tier 4) with app-specific action libraries. Vision-based UI parsing for apps without accessibility APIs.", "effort": "1 month"},
                {"id": "process_management", "name": "Process and system management",
                 "description": "Start/stop processes, monitor system health, manage dev environment, restart services.",
                 "how_to_unlock": "Add psutil tools: list_processes, kill_process, get_system_stats, restart_service. Expose via tool-use with risk-gating.", "effort": "1 month"},
                {"id": "autonomous_deploy", "name": "Autonomous code deployment pipeline",
                 "description": "Low-risk changes: Tobi codes → tests → deploys without human involvement. Gate only on high-risk or strategic changes.",
                 "how_to_unlock": "Wire coding agent to: write code, run tests, interpret results, deploy if passing and risk_low.", "effort": "1 month"},
            ],
            "presence": [
                {"id": "background_monitoring", "name": "Background monitoring of all systems",
                 "description": "Tobi watches servers, revenue, codebase, inbox 24/7 — not just at scheduled intervals.",
                 "how_to_unlock": "Replace cron scheduler with event-driven daemon. Continuous polling with smart intervals. State diffing for change detection.", "effort": "1 month"},
                {"id": "anomaly_detection", "name": "Anomaly detection + intelligent alerting",
                 "description": "Server down? Revenue drop? Unusual error spike? Tobi tells you before it becomes a crisis.",
                 "how_to_unlock": "Baseline + threshold tracking for key metrics. Statistical anomaly detection. Telegram alert with context + suggested action.", "effort": "1 month"},
                {"id": "context_aware_interrupts", "name": "Context-aware interruption logic",
                 "description": "Tobi knows when you're in deep work and only interrupts for genuinely urgent things. Smart notification scheduling.",
                 "how_to_unlock": "Add do_not_disturb mode. Track active hours from interaction patterns. Batch non-urgent alerts to check-in times.", "effort": "1 month"},
            ],
        },
    },
    {
        "id": 6, "roman": "VI", "name": "ARCHITECT", "color_key": "aurora",
        "tagline": "Tobi builds its own new capabilities and runs your life.",
        "pillars": {
            "understand": [
                {"id": "strategic_advisor", "name": "Strategic advisor (not just executor)",
                 "description": "Tobi challenges your assumptions, proposes alternatives, and acts as a genuine thought partner — not just a task runner.",
                 "how_to_unlock": "Add devil's advocate mode to planning. Tobi generates counter-proposals for major decisions. Weekly strategy review initiated by Tobi.", "effort": "1 month"},
                {"id": "full_history_synthesis", "name": "Full history synthesis",
                 "description": "Tobi synthesizes insights across all past interactions, projects, and decisions into a coherent strategic view.",
                 "how_to_unlock": "Monthly synthesis job: read all lessons + projects + outcomes. LLM generates strategic narrative. Store as strategic_context in profile.", "effort": "1 month"},
            ],
            "control": [
                {"id": "self_integration", "name": "Writes and deploys its own integrations",
                 "description": "Tobi identifies a capability gap, writes the integration code, tests it, adds it to its own tool set without human involvement.",
                 "how_to_unlock": "Extend coding agent to target its own codebase. Add self_improve() proposing new tools. Gate first deployment on owner approval.", "effort": "1 month"},
                {"id": "ten_project_portfolio", "name": "10+ active project portfolio management",
                 "description": "Managing 10+ simultaneous projects with autonomous execution, cross-project resource allocation, portfolio-level optimization.",
                 "how_to_unlock": "Portfolio-level scheduler balancing agent time across projects based on ROI and strategic priority.", "effort": "1 month"},
                {"id": "full_dev_loop", "name": "Owns the full development loop",
                 "description": "Feature request → design → code → test → deploy. End-to-end with human review gates at design and deploy only.",
                 "how_to_unlock": "Chain: design_proposal(task) → owner_approve → code_it() → run_tests() → deploy_if_passing(). Two approval gates, rest automated.", "effort": "1 month"},
            ],
            "presence": [
                {"id": "multi_device", "name": "Multi-device synchronized presence",
                 "description": "Tobi on your phone, laptop, and desktop — synchronized state, consistent experience, context-aware channel selection.",
                 "how_to_unlock": "Cloud-sync conversation state and user profile. Mobile PWA. WebSocket for real-time sync across devices.", "effort": "1 month"},
                {"id": "autonomous_delegation", "name": "Autonomous sub-agent delegation",
                 "description": "Tobi spawns specialized sub-agents without being prompted — research, coder, CEO agents all working in parallel on your behalf.",
                 "how_to_unlock": "Extend multi-agent parallelism (Tier 4). Tobi autonomously decides when to delegate, budget-gated by token limits.", "effort": "1 month"},
                {"id": "self_improving_skills", "name": "Self-improving Hermes skill system",
                 "description": "Tobi writes and improves its own Hermes skill files based on performance. Every success and failure feeds back into operating playbooks.",
                 "how_to_unlock": "Add skill_update(skill_id, improvement). Weekly review of skill performance metrics triggers rewrites.", "effort": "1 month"},
            ],
        },
    },
    {
        "id": 7, "roman": "VII", "name": "SOVEREIGN", "color_key": "sovereign",
        "tagline": "Full Jarvis. The mission complete. Tony Stark would be proud.",
        "pillars": {
            "understand": [
                {"id": "complete_mind_model", "name": "Complete mind-model of owner",
                 "description": "Tobi knows your context, history, preferences, goals, relationships, and decision patterns without being told anything.",
                 "how_to_unlock": "The culmination of all Understand Me pillars. Requires years of interaction data + sophisticated inference. Not a feature — an emergent property.", "effort": "???"},
                {"id": "zero_repeat_yourself", "name": "Never need to repeat yourself",
                 "description": "If you've said it to Tobi once, it remembers and applies it forever. Zero re-explanation needed.",
                 "how_to_unlock": "Entity extraction (T1) + semantic memory (T2) + episodic memory (T3), all fully mature and combined.", "effort": "???"},
            ],
            "control": [
                {"id": "unrestricted_control", "name": "Unrestricted PC control with judgment",
                 "description": "If a human can do it on the PC, Tobi can do it. Intelligent risk assessment replaces hard limits.",
                 "how_to_unlock": "Culmination of all PC Control pillars + a sophisticated risk model trained on your specific risk preferences.", "effort": "???"},
                {"id": "real_money_machine", "name": "Self-sustaining revenue engine",
                 "description": "Tobi runs the full MMO portfolio autonomously — research, execute, optimize, reinvest. Revenue without your involvement.",
                 "how_to_unlock": "All revenue pipeline capabilities (T3) + autonomous decision-making (T4+) + portfolio management (T6) combined.", "effort": "???"},
                {"id": "any_digital_task", "name": "Execute any digital task",
                 "description": "Give Tobi any task a PC user could accomplish. It figures out the steps, delegates, and completes it.",
                 "how_to_unlock": "Full tool surface + multi-agent orchestration + reliable task completion. Emergent from all PC Control capabilities.", "effort": "???"},
            ],
            "presence": [
                {"id": "true_jarvis", "name": "True Jarvis presence",
                 "description": "Voice-ready, cross-device, always-on, proactively helpful, context-aware 24/7. The Tony Stark experience, realized.",
                 "how_to_unlock": "The culmination of all Always-On Presence pillars. Voice + multi-device + proactive + always-on combined.", "effort": "???"},
                {"id": "self_improvement_loop", "name": "Autonomous self-improvement loop",
                 "description": "Tobi identifies its own capability gaps, builds solutions, tests them, integrates them. Compounding capability growth without direction.",
                 "how_to_unlock": "Combines self-integration (T6) + performance monitoring + autonomous deployment. Tobi improves itself on a weekly cycle.", "effort": "???"},
            ],
        },
    },
]


def _detect_abilities(conn: sqlite3.Connection) -> dict[str, bool]:
    repo_root = Path(__file__).parent.parent

    def env(key: str) -> bool:
        return bool(os.getenv(key))

    def file_ok(rel: str) -> bool:
        p = repo_root / rel
        return p.exists() and p.stat().st_size > 50

    def db_has_rows(table: str, where: str = "") -> bool:
        try:
            q = f"SELECT 1 FROM {table}" + (f" WHERE {where}" if where else "") + " LIMIT 1"
            return conn.execute(q).fetchone() is not None
        except Exception:
            return False

    has_llm = env("ANTHROPIC_API_KEY") or env("OPENROUTER_API_KEY")
    has_bot = env("TELEGRAM_BOT_TOKEN")

    # TOBI CLI (#11) delivers the Awakening control abilities: the two-axis permission model
    # replaces the old _BLOCKED_CMDS denylist, and full-machine scope replaces the PROJECT_DIR
    # lock. Evidence = the terminal engine module is present [D30].
    terminal_ready = file_ok("core/terminal_engine.py")

    return {
        # Tier 0
        "soul_md": file_ok("SOUL.md"),
        "conversation_history": db_has_rows("conversations"),
        "task_classifier": True,
        "lessons_store": db_has_rows("lessons"),
        "coding_agent": env("ANTHROPIC_API_KEY"),
        "github_integration": env("GITHUB_TOKEN"),
        "notion_integration": env("NOTION_API_KEY"),
        "vercel_integration": env("VERCEL_TOKEN"),
        "supabase_integration": env("SUPABASE_URL"),
        "google_oauth": env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"),
        "gmail_integration": env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"),
        "calendar_integration": env("GOOGLE_CLIENT_ID") and env("GOOGLE_CLIENT_SECRET"),
        "telegram_bot": has_bot,
        "cron_scheduler": has_bot and has_llm,
        "proactive_reports": has_bot and has_llm,
        # Tier 1 (Awakening) control abilities delivered by the terminal engine (#11)
        "tiered_permissions": terminal_ready,
        "full_filesystem": terminal_ready,
        # Remaining Tier 1+ abilities default to False (not yet built)
    }


_ABILITY_NAMES = {
    ab["id"]: ab["name"]
    for tier in _TIER_DEFINITIONS
    for pillar in tier["pillars"].values()
    for ab in pillar
}
