"""
HERMES SYNC — Premium Chat (#8 P1).

Mission Control's Models page is the **single source of truth** for LLM routing. On
save we **push** the chosen models to Hermes (MC → Hermes, one-way) so the always-on
Hermes runtime and TOBI's own router stay aligned.

Three best-effort writes, in order of reliability — every one is wrapped so a failure
never crashes the chat or the config save:

1. **JSON sidecar** ``~/.hermes/config/tobi_models.json`` — always works, machine-readable.
2. **YAML patch** of ``~/.hermes/config/hermes.yaml`` ``cost_optimization.model_routing``
   (only if PyYAML is importable; skipped silently otherwise).
3. **CLI** ``hermes config set …`` for the primary / secondary endpoints (only if a
   ``hermes`` binary is on PATH).

See HERMES_COST_OPTIMIZATION.md for the target config shape.
"""
from __future__ import annotations

import os
import json
import shutil
import logging
import subprocess
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("tobi.hermes_sync")

_HERMES_DIR = os.path.join(os.path.expanduser("~"), ".hermes", "config")
_JSON_PATH = os.path.join(_HERMES_DIR, "tobi_models.json")
_YAML_PATH = os.path.join(_HERMES_DIR, "hermes.yaml")
CAPABILITY_CONTRACT_VERSION = "1"

# Map TOBI task types → the Hermes routing buckets used in hermes.yaml.
_TASK_TO_HERMES = {
    "simple": "simple_questions",
    "default": "normal_tasks",
    "writing": "normal_tasks",
    "research": "web_research",
    "planning": "complex_reasoning",
    "ceo_review": "complex_reasoning",
    "coding": "normal_tasks",
}


def capability_source() -> dict:
    """Metadata-only declaration for the MC worker-capability adapter."""
    return {
        "source_id": "hermes-model-routing-sync",
        "contract_version": CAPABILITY_CONTRACT_VERSION,
        "authority": "mission_control",
        "direction": "mc_to_hermes",
        "can_own_runtime": False,
        "capabilities": ("model_routing_mirror",),
    }


def _routing(cfg: dict) -> dict:
    """Build a {hermes_bucket: model_id} routing map from a TOBI llm_config."""
    default = cfg.get("default_model") or ""
    overrides = cfg.get("task_overrides") or {}
    routing: dict[str, str] = {}
    if default:
        for bucket in ("simple_questions", "normal_tasks", "complex_reasoning", "web_research"):
            routing[bucket] = default
    for task, model in overrides.items():
        bucket = _TASK_TO_HERMES.get(task)
        if bucket and model:
            routing[bucket] = model
    return routing


def _bare_model(model_id: str) -> str:
    """'provider:model' → 'model' (Hermes/Ollama want the raw name)."""
    return model_id.split(":", 1)[1] if ":" in model_id else model_id


def _write_json(cfg: dict, routing: dict) -> bool:
    try:
        os.makedirs(_HERMES_DIR, exist_ok=True)
        payload = {
            "source": "tobi-mission-control",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "default_model": cfg.get("default_model") or "",
            "task_overrides": cfg.get("task_overrides") or {},
            "fallback": cfg.get("fallback") or [],
            "model_routing": routing,
        }
        with open(_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.warning("hermes json sidecar failed: %s", e)
        return False


def _patch_yaml(routing: dict) -> bool:
    try:
        import yaml  # type: ignore
    except Exception:
        return False
    try:
        os.makedirs(_HERMES_DIR, exist_ok=True)
        data = {}
        if os.path.exists(_YAML_PATH):
            with open(_YAML_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            data = {}
        co = data.setdefault("cost_optimization", {})
        if not isinstance(co, dict):
            co = {}
            data["cost_optimization"] = co
        co["enable_hybrid_models"] = True
        co["model_routing"] = {k: _bare_model(v) for k, v in routing.items()}
        with open(_YAML_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
        return True
    except Exception as e:
        logger.warning("hermes yaml patch failed: %s", e)
        return False


def _cli_set(cfg: dict) -> bool:
    exe = shutil.which("hermes")
    if not exe:
        return False
    default = cfg.get("default_model") or ""
    if not default:
        return False
    ok = False
    try:
        # Primary model name (Hermes resolves the endpoint from its own provider config).
        subprocess.run([exe, "config", "set", "primary_model_name", _bare_model(default)],
                       timeout=15, capture_output=True)
        ok = True
        # If a local Ollama model is in the fallback chain, wire it as the secondary endpoint.
        for fb in cfg.get("fallback") or []:
            if fb.startswith("ollama:"):
                subprocess.run([exe, "config", "set", "secondary_model_endpoint",
                                "http://localhost:11434/v1"], timeout=15, capture_output=True)
                subprocess.run([exe, "config", "set", "secondary_model_name", _bare_model(fb)],
                               timeout=15, capture_output=True)
                break
    except Exception as e:
        logger.warning("hermes cli set failed: %s", e)
    return ok


def push_config(cfg: Optional[dict] = None) -> dict:
    """Push the current (or given) routing config to Hermes. Always returns a summary;
    never raises."""
    if cfg is None:
        try:
            from core.model_router import load_llm_config
            cfg = load_llm_config()
        except Exception:
            cfg = {}
    routing = _routing(cfg or {})
    json_ok = _write_json(cfg or {}, routing)
    yaml_ok = _patch_yaml(routing)
    cli_ok = _cli_set(cfg or {})
    targets = [t for t, ok in (("json", json_ok), ("yaml", yaml_ok), ("cli", cli_ok)) if ok]
    return {
        "ok": json_ok or yaml_ok or cli_ok,
        "json": json_ok, "yaml": yaml_ok, "cli": cli_ok,
        "targets": targets,
        "routing": routing,
        "detail": ("Pushed to Hermes: " + ", ".join(targets)) if targets
                  else "Hermes config not found — wrote nothing (is Hermes installed?).",
    }
