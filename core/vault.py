"""Encrypted secrets vault — Tobi "Genesis Complete".

Stores API keys / tokens encrypted at rest in SQLite and overlays them onto
``os.environ`` once unlocked, so all existing ``os.getenv`` callers keep working.

Security model
--------------
- Master password → **scrypt** KDF (salt + params in ``vault_meta``) → 32-byte key.
- Each secret encrypted with **AES-256-GCM** (per-secret nonce, AAD = the env-var
  name so ciphertext can't be moved between names).
- A **verifier** blob (AES-GCM of a known constant) validates the password on
  unlock without ever storing it.
- The derived key lives **only in process memory** while unlocked, and is cleared
  on lock or after inactivity (auto-relock). Revealing a value re-requires the
  master password.
- Secret *values* are never logged; ``vault_audit`` records metadata only.

Losing the master password makes the vault unrecoverable by design — mitigated by
the password-protected export/import.
"""
from __future__ import annotations

import os
import json
import time
import base64
import secrets as _secrets
import sqlite3
from datetime import datetime, timezone
from typing import Optional

try:  # crypto is required for the vault, but must not break app import if absent
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.exceptions import InvalidTag
    CRYPTO_AVAILABLE = True
except Exception:  # pragma: no cover - only when cryptography missing
    AESGCM = None  # type: ignore
    Scrypt = None  # type: ignore
    InvalidTag = Exception  # type: ignore
    CRYPTO_AVAILABLE = False

# ── tunables ────────────────────────────────────────────────────────────
_SCRYPT_N = 2 ** 15          # 32768 — strong but ~50ms, fine for an unlock action
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LEN = 32               # AES-256
_NONCE_LEN = 12
_VERIFY_CONST = b"tobi-vault-verify-v1"
AUTO_LOCK_SECONDS = 15 * 60  # relock after this much inactivity

# env-var NAMEs imported from the current environment on first-run setup
KNOWN_ENV_KEYS = [
    "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY",
    "TELEGRAM_BOT_TOKEN", "GITHUB_TOKEN", "NOTION_API_KEY",
    "VERCEL_TOKEN", "SUPABASE_URL", "SUPABASE_ANON_KEY",
    "TAVILY_API_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI", "CODEX_ACCESS_TOKEN", "CODEX_CHATGPT_ACCOUNT_ID",
]


class VaultError(Exception):
    """Generic vault failure (bad password, locked, crypto missing…)."""


class VaultLocked(VaultError):
    pass


# ── in-memory unlock session (never persisted) ──────────────────────────
_key: Optional[bytes] = None
_session_token: Optional[str] = None
_last_activity: float = 0.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_crypto() -> None:
    if not CRYPTO_AVAILABLE:
        raise VaultError("The 'cryptography' package is not installed — run: pip install cryptography")


# ── KDF + verifier ──────────────────────────────────────────────────────
def _derive_key(master: str, salt: bytes, params: dict) -> bytes:
    kdf = Scrypt(salt=salt, length=params.get("len", _KEY_LEN),
                 n=params.get("n", _SCRYPT_N), r=params.get("r", _SCRYPT_R), p=params.get("p", _SCRYPT_P))
    return kdf.derive(master.encode("utf-8"))


def _make_verifier(key: bytes) -> bytes:
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, _VERIFY_CONST, b"verifier")
    return nonce + ct


def _check_verifier(key: bytes, verifier: bytes) -> bool:
    try:
        nonce, ct = verifier[:_NONCE_LEN], verifier[_NONCE_LEN:]
        return AESGCM(key).decrypt(nonce, ct, b"verifier") == _VERIFY_CONST
    except InvalidTag:
        return False
    except Exception:
        return False


def _encrypt(key: bytes, name: str, value: str) -> tuple[bytes, bytes]:
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, value.encode("utf-8"), name.encode("utf-8"))
    return ct, nonce


def _decrypt(key: bytes, name: str, ciphertext: bytes, nonce: bytes) -> str:
    return AESGCM(key).decrypt(nonce, ciphertext, name.encode("utf-8")).decode("utf-8")


def _last4(value: str) -> str:
    v = value.strip()
    return v[-4:] if len(v) > 8 else "••••"


# ── audit ───────────────────────────────────────────────────────────────
def _audit(conn: sqlite3.Connection, action: str, *, integration_id: str | None = None,
           name: str | None = None, ok: bool | None = None, detail: str | None = None) -> None:
    try:
        conn.execute(
            "INSERT INTO vault_audit (ts, action, integration_id, name, ok, detail) VALUES (?,?,?,?,?,?)",
            (_now(), action, integration_id, name, None if ok is None else int(ok), detail),
        )
        conn.commit()
    except Exception:
        pass  # auditing must never break the operation


def get_audit(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT ts, action, integration_id, name, ok, detail FROM vault_audit ORDER BY id DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [
        {"ts": r[0], "action": r[1], "integration_id": r[2], "name": r[3],
         "ok": None if r[4] is None else bool(r[4]), "detail": r[5]}
        for r in rows
    ]


# ── meta / setup state ──────────────────────────────────────────────────
def _meta(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    try:
        return conn.execute("SELECT * FROM vault_meta WHERE id = 1").fetchone()
    except Exception:
        return None


def is_setup(conn: sqlite3.Connection) -> bool:
    return _meta(conn) is not None


def active_profile(conn: sqlite3.Connection) -> str:
    m = _meta(conn)
    return (m["active_profile"] if m else None) or "local"


# ── session ─────────────────────────────────────────────────────────────
def is_unlocked() -> bool:
    global _key, _session_token, _last_activity
    if _key is None:
        return False
    if time.time() - _last_activity > AUTO_LOCK_SECONDS:
        lock()
        return False
    return True


def _touch() -> None:
    global _last_activity
    _last_activity = time.time()


def require_session(token: str | None) -> None:
    """Gate for vault endpoints: a valid, unexpired session token."""
    if not is_unlocked() or not token or token != _session_token:
        raise VaultLocked("Vault is locked — unlock with the master password.")
    _touch()


def lock() -> None:
    global _key, _session_token, _last_activity
    _key = None
    _session_token = None
    _last_activity = 0.0


def _new_session() -> str:
    global _session_token
    _session_token = _secrets.token_urlsafe(32)
    _touch()
    return _session_token


# ── setup / unlock ──────────────────────────────────────────────────────
def setup(conn: sqlite3.Connection, master: str, *, import_env: bool = True) -> str:
    """First-run: pick a master password, create the KDF salt + verifier, optionally
    import existing env keys, and leave the vault unlocked. Returns a session token."""
    _require_crypto()
    if not master or len(master) < 6:
        raise VaultError("Master password must be at least 6 characters.")
    if is_setup(conn):
        raise VaultError("Vault is already set up — unlock instead.")
    global _key
    salt = os.urandom(16)
    params = {"n": _SCRYPT_N, "r": _SCRYPT_R, "p": _SCRYPT_P, "len": _KEY_LEN}
    key = _derive_key(master, salt, params)
    verifier = _make_verifier(key)
    conn.execute(
        "INSERT INTO vault_meta (id, kdf, kdf_salt, kdf_params, verifier, active_profile, created_at) "
        "VALUES (1, 'scrypt', ?, ?, ?, 'local', ?)",
        (salt, json.dumps(params), verifier, _now()),
    )
    conn.execute("INSERT OR IGNORE INTO vault_profiles (name, label, created_at) VALUES ('local', 'Local', ?)",
                 (_now(),))
    conn.commit()
    _key = key
    _new_session()
    _audit(conn, "setup", detail="vault created")
    if import_env:
        imported = import_from_env(conn)
        _audit(conn, "import", detail=f"imported {imported} key(s) from environment")
    enable_autounlock(conn)  # so integrations auto-connect on every future startup
    return _session_token  # type: ignore[return-value]


def unlock(conn: sqlite3.Connection, master: str) -> str:
    """Validate the master password against the verifier; cache the key + return a token."""
    _require_crypto()
    m = _meta(conn)
    if m is None:
        raise VaultError("Vault is not set up yet.")
    global _key
    params = json.loads(m["kdf_params"])
    key = _derive_key(master, m["kdf_salt"], params)
    if not _check_verifier(key, m["verifier"]):
        _audit(conn, "unlock", ok=False, detail="wrong password")
        raise VaultError("Incorrect master password.")
    _key = key
    token = _new_session()
    _audit(conn, "unlock", ok=True)
    enable_autounlock(conn)  # refresh the cached key so future startups auto-connect
    return token


def _key_from_master(conn: sqlite3.Connection, master: str) -> bytes:
    """Re-derive + verify a key from a freshly-entered master password (for reveal)."""
    m = _meta(conn)
    if m is None:
        raise VaultError("Vault is not set up yet.")
    key = _derive_key(master, m["kdf_salt"], json.loads(m["kdf_params"]))
    if not _check_verifier(key, m["verifier"]):
        raise VaultError("Incorrect master password.")
    return key


def verify_master(conn: sqlite3.Connection, master: str) -> bool:
    """Verify a freshly entered master password without revealing a secret."""
    _key_from_master(conn, master)
    return True


# ── secret CRUD ─────────────────────────────────────────────────────────
def set_secret(conn: sqlite3.Connection, name: str, value: str, *, integration_id: str | None = None,
               secret_type: str = "api_key", profile: str | None = None, test_status: str | None = None) -> None:
    if _key is None:
        raise VaultLocked("Vault is locked.")
    name = name.strip()
    if not name:
        raise VaultError("Secret name is required.")
    prof = profile or active_profile(conn)
    ct, nonce = _encrypt(_key, name, value)
    status = test_status or "untested"
    if status not in {"untested", "ok", "failed"}:
        raise VaultError("Invalid secret test status.")
    tested_at = _now() if status in {"ok", "failed"} else None
    existing = conn.execute("SELECT id FROM vault_secrets WHERE profile = ? AND name = ?", (prof, name)).fetchone()
    if existing:
        conn.execute(
            "UPDATE vault_secrets SET ciphertext=?, nonce=?, last4=?, integration_id=COALESCE(?, integration_id), "
            "secret_type=?, updated_at=?, test_status=?, last_tested_at=? WHERE id=?",
            (ct, nonce, _last4(value), integration_id, secret_type, _now(), status, tested_at, existing[0]),
        )
        action = "update"
    else:
        conn.execute(
            "INSERT INTO vault_secrets (profile, name, integration_id, secret_type, ciphertext, nonce, last4, "
            "test_status, added_at, updated_at, last_tested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (prof, name, integration_id, secret_type, ct, nonce, _last4(value),
             status, _now(), _now(), tested_at),
        )
        action = "create"
    conn.commit()
    _audit(conn, action, integration_id=integration_id, name=name, ok=True)


def get_secret(conn: sqlite3.Connection, name: str, profile: str | None = None) -> Optional[str]:
    if _key is None:
        raise VaultLocked("Vault is locked.")
    prof = profile or active_profile(conn)
    row = conn.execute("SELECT ciphertext, nonce FROM vault_secrets WHERE profile=? AND name=?", (prof, name)).fetchone()
    if not row:
        return None
    return _decrypt(_key, name, row[0], row[1])


def delete_secret(conn: sqlite3.Connection, name: str, *, integration_id: str | None = None,
                  profile: str | None = None) -> None:
    prof = profile or active_profile(conn)
    conn.execute("DELETE FROM vault_secrets WHERE profile=? AND name=?", (prof, name))
    conn.commit()
    # remove the live override too so detection reflects the deletion
    if name in os.environ:
        try:
            del os.environ[name]
        except Exception:
            pass
    _audit(conn, "delete", integration_id=integration_id, name=name, ok=True)


def list_secrets(conn: sqlite3.Connection, profile: str | None = None) -> list[dict]:
    """Metadata only — never the value."""
    prof = profile or active_profile(conn)
    rows = conn.execute(
        "SELECT name, integration_id, secret_type, last4, test_status, added_at, updated_at, last_tested_at "
        "FROM vault_secrets WHERE profile=? ORDER BY name", (prof,)
    ).fetchall()
    return [
        {"name": r[0], "integration_id": r[1], "secret_type": r[2], "last4": r[3],
         "test_status": r[4], "added_at": r[5], "updated_at": r[6], "last_tested_at": r[7]}
        for r in rows
    ]


def mark_tested(conn: sqlite3.Connection, name: str, ok: bool, profile: str | None = None) -> None:
    prof = profile or active_profile(conn)
    conn.execute("UPDATE vault_secrets SET test_status=?, last_tested_at=? WHERE profile=? AND name=?",
                 ("ok" if ok else "failed", _now(), prof, name))
    conn.commit()


def mark_test_status(conn: sqlite3.Connection, name: str, status: str,
                     profile: str | None = None) -> None:
    """Set explicit test state; untested intentionally clears stale success evidence."""
    if status not in {"untested", "ok", "failed"}:
        raise VaultError("Invalid secret test status.")
    prof = profile or active_profile(conn)
    tested_at = _now() if status in {"ok", "failed"} else None
    conn.execute(
        "UPDATE vault_secrets SET test_status=?, last_tested_at=? WHERE profile=? AND name=?",
        (status, tested_at, prof, name),
    )
    conn.commit()


def reveal(conn: sqlite3.Connection, name: str, master: str, profile: str | None = None) -> str:
    """Return a full secret value — requires re-entering the master password."""
    _require_crypto()
    key = _key_from_master(conn, master)  # raises on wrong password
    prof = profile or active_profile(conn)
    row = conn.execute("SELECT ciphertext, nonce FROM vault_secrets WHERE profile=? AND name=?", (prof, name)).fetchone()
    if not row:
        raise VaultError("No such secret.")
    value = _decrypt(key, name, row[0], row[1])
    _audit(conn, "reveal", name=name, ok=True)
    return value


# ── env injection (consumption) ─────────────────────────────────────────
def inject_env(conn: sqlite3.Connection, profile: str | None = None) -> int:
    """Overlay the active profile's secrets onto os.environ (vault wins; .env is the
    fallback for anything not in the vault). Idempotent. Requires an unlocked vault.
    Key-slot alternates (names containing '::') are storage-only and are skipped —
    only the plain, active secret for each env var is injected."""
    if _key is None:
        raise VaultLocked("Vault is locked.")
    prof = profile or active_profile(conn)
    rows = conn.execute("SELECT name, ciphertext, nonce FROM vault_secrets WHERE profile=?", (prof,)).fetchall()
    n = 0
    for name, ct, nonce in rows:
        if SLOT_SEP in name:
            continue
        try:
            os.environ[name] = _decrypt(_key, name, ct, nonce)
            n += 1
        except Exception:
            pass
    return n


# ── key slots: multiple values per secret, one active at a time ──────────
# Each alternate account key for a secret NAME is stored as its own encrypted
# secret named "NAME::<label>". The plain secret NAME always holds the ACTIVE
# value (so inject_env / model_router / integrations stay unchanged); which
# label is active is tracked in owner_settings under "vault.active_slot.NAME".
SLOT_SEP = "::"


def _slot_setting_key(name: str) -> str:
    return f"vault.active_slot.{name}"


def _ensure_owner_settings(conn: sqlite3.Connection) -> None:
    from core import owner_flags
    owner_flags.ensure_schema(conn)  # canonical wide shape; caller owns commit/close


def _get_active_label(conn: sqlite3.Connection, name: str) -> Optional[str]:
    _ensure_owner_settings(conn)
    row = conn.execute("SELECT value FROM owner_settings WHERE key=?", (_slot_setting_key(name),)).fetchone()
    return row[0] if row else None


def _set_active_label(conn: sqlite3.Connection, name: str, label: Optional[str]) -> None:
    _ensure_owner_settings(conn)
    if label is None:
        conn.execute("DELETE FROM owner_settings WHERE key=?", (_slot_setting_key(name),))
    else:
        conn.execute(
            "INSERT INTO owner_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (_slot_setting_key(name), label),
        )
    conn.commit()


def _migrate_plain_to_slot(conn: sqlite3.Connection, name: str, profile: str | None = None) -> None:
    """If a lone pre-multi-key secret exists (plain NAME, no slots), copy it into
    slot 'Key 1' and mark that active — so the owner's first key shows in the list."""
    prof = profile or active_profile(conn)
    slots = [s for s in list_secrets(conn, prof) if s["name"].startswith(name + SLOT_SEP)]
    if slots:
        return
    val = get_secret(conn, name, prof)
    if val is None:
        return
    set_secret(conn, f"{name}{SLOT_SEP}Key 1", val, integration_id="keyslot",
               secret_type="api_key", profile=prof)
    _set_active_label(conn, name, "Key 1")


def list_key_slots(conn: sqlite3.Connection, name: str, profile: str | None = None) -> list[dict]:
    """Metadata for every stored key of NAME (never values). Migrates a lone plain
    secret into 'Key 1' first, so pre-existing single keys appear in the list."""
    if _key is None:
        raise VaultLocked("Vault is locked.")
    prof = profile or active_profile(conn)
    _migrate_plain_to_slot(conn, name, prof)
    active = _get_active_label(conn, name)
    plain_present = conn.execute(
        "SELECT 1 FROM vault_secrets WHERE profile=? AND name=?", (prof, name)).fetchone() is not None
    out = []
    for s in list_secrets(conn, prof):
        if not s["name"].startswith(name + SLOT_SEP):
            continue
        label = s["name"][len(name) + len(SLOT_SEP):]
        out.append({
            "label": label, "last4": s["last4"], "env": False,
            "active": plain_present and label == active,
            "added_at": s["added_at"], "updated_at": s["updated_at"],
        })
    # A key that lives only in .env (os.environ, never stored in the vault) has no slot
    # above — surface it as a read-only ACTIVE entry so it's visible/censored in the UI.
    # Skip when a vault slot is already active (that value overrides the env one).
    if not any(o["active"] for o in out):
        envval = os.environ.get(name)
        if envval:
            out.insert(0, {"label": "Current (.env)", "last4": envval[-4:], "env": True,
                           "active": True, "added_at": None, "updated_at": None})
    return out


def add_key_slot(conn: sqlite3.Connection, name: str, value: str, label: str | None = None,
                 activate: bool = False, profile: str | None = None) -> str:
    """Store an additional key for NAME under a label ('Key N' if omitted). Activates it
    when asked — or automatically when it's the only key. Returns the label used."""
    if _key is None:
        raise VaultLocked("Vault is locked.")
    prof = profile or active_profile(conn)
    _migrate_plain_to_slot(conn, name, prof)
    existing = {s["label"] for s in list_key_slots(conn, name, prof)}
    label = (label or "").strip().replace(SLOT_SEP, " ")
    if not label:
        n = 1
        while f"Key {n}" in existing:
            n += 1
        label = f"Key {n}"
    set_secret(conn, f"{name}{SLOT_SEP}{label}", value, integration_id="keyslot",
               secret_type="api_key", profile=prof)
    if activate or not existing:  # first key ever → it's the active one
        activate_key_slot(conn, name, label, prof)
    return label


def activate_key_slot(conn: sqlite3.Connection, name: str, label: str, profile: str | None = None) -> None:
    """One active at a time: copy the slot's value into the plain secret NAME (which
    inject_env feeds to os.environ) and point the active marker at this label."""
    prof = profile or active_profile(conn)
    val = get_secret(conn, f"{name}{SLOT_SEP}{label}", prof)
    if val is None:
        raise VaultError(f"No key labeled '{label}' for {name}.")
    set_secret(conn, name, val, integration_id="llm", secret_type="api_key", profile=prof)
    _set_active_label(conn, name, label)
    os.environ[name] = val
    _audit(conn, "slot_activate", name=f"{name}{SLOT_SEP}{label}", ok=True)


def deactivate_key_slots(conn: sqlite3.Connection, name: str, profile: str | None = None) -> None:
    """Turn the active key OFF without deleting it — removes the plain secret + live
    env var, so the provider reads as disconnected until another slot is activated."""
    prof = profile or active_profile(conn)
    delete_secret(conn, name, integration_id="keyslot", profile=prof)
    _set_active_label(conn, name, None)


def delete_key_slot(conn: sqlite3.Connection, name: str, label: str, profile: str | None = None) -> None:
    """Remove a stored key. Deleting the active one promotes the first remaining
    slot (keeps the provider working) or fully deactivates when none remain."""
    prof = profile or active_profile(conn)
    was_active = _get_active_label(conn, name) == label
    delete_secret(conn, f"{name}{SLOT_SEP}{label}", integration_id="keyslot", profile=prof)
    if was_active:
        # Clear the plain (live) copy FIRST — otherwise the migration shim in
        # list_key_slots would see it and resurrect the just-deleted key as a slot.
        deactivate_key_slots(conn, name, prof)
        remaining = [s for s in list_secrets(conn, prof) if s["name"].startswith(name + SLOT_SEP)]
        if remaining:
            activate_key_slot(conn, name, remaining[0]["name"][len(name) + len(SLOT_SEP):], prof)


def reload(conn: sqlite3.Connection) -> int:
    n = inject_env(conn)
    _audit(conn, "reload", detail=f"re-injected {n} key(s)")
    return n


def import_from_env(conn: sqlite3.Connection, names: list[str] | None = None) -> int:
    """First-run migration: copy present environment values into the vault."""
    if _key is None:
        raise VaultLocked("Vault is locked.")
    count = 0
    for name in (names or KNOWN_ENV_KEYS):
        val = os.getenv(name)
        if val:
            stype = "url" if name.endswith("_URL") else "api_key"
            set_secret(conn, name, val, secret_type=stype)
            count += 1
    return count


# ── profiles ────────────────────────────────────────────────────────────
def list_profiles(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT name, label, created_at FROM vault_profiles ORDER BY created_at").fetchall()
    out = [{"name": r[0], "label": r[1], "created_at": r[2]} for r in rows]
    if not out:
        out = [{"name": "local", "label": "Local", "created_at": None}]
    return out


def create_profile(conn: sqlite3.Connection, name: str, label: str | None = None) -> None:
    name = name.strip().lower()
    if not name:
        raise VaultError("Profile name is required.")
    conn.execute("INSERT OR IGNORE INTO vault_profiles (name, label, created_at) VALUES (?,?,?)",
                 (name, label or name.title(), _now()))
    conn.commit()


def set_active_profile(conn: sqlite3.Connection, name: str) -> None:
    name = name.strip().lower()
    conn.execute("INSERT OR IGNORE INTO vault_profiles (name, label, created_at) VALUES (?,?,?)",
                 (name, name.title(), _now()))
    conn.execute("UPDATE vault_meta SET active_profile=? WHERE id=1", (name,))
    conn.commit()
    if is_unlocked():
        inject_env(conn, name)


# ── export / import (password-protected backup) ─────────────────────────
def export_blob(conn: sqlite3.Connection, password: str) -> str:
    """Encrypt all secrets (all profiles) under a fresh password → portable base64 blob."""
    _require_crypto()
    if _key is None:
        raise VaultLocked("Vault is locked.")
    if not password or len(password) < 6:
        raise VaultError("Export password must be at least 6 characters.")
    rows = conn.execute("SELECT profile, name, integration_id, secret_type, ciphertext, nonce FROM vault_secrets").fetchall()
    items = []
    for prof, name, iid, stype, ct, nonce in rows:
        items.append({"profile": prof, "name": name, "integration_id": iid,
                      "secret_type": stype, "value": _decrypt(_key, name, ct, nonce)})
    plaintext = json.dumps({"version": 1, "items": items}).encode("utf-8")
    salt = os.urandom(16)
    params = {"n": _SCRYPT_N, "r": _SCRYPT_R, "p": _SCRYPT_P, "len": _KEY_LEN}
    ekey = _derive_key(password, salt, params)
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(ekey).encrypt(nonce, plaintext, b"vault-export")
    blob = {"v": 1, "salt": base64.b64encode(salt).decode(), "params": params,
            "nonce": base64.b64encode(nonce).decode(), "ct": base64.b64encode(ct).decode()}
    _audit(conn, "export", detail=f"{len(items)} secret(s)")
    return base64.b64encode(json.dumps(blob).encode("utf-8")).decode("utf-8")


def import_blob(conn: sqlite3.Connection, blob_b64: str, password: str) -> int:
    """Restore secrets from an export blob into the current vault (re-encrypted)."""
    _require_crypto()
    if _key is None:
        raise VaultLocked("Vault is locked.")
    try:
        blob = json.loads(base64.b64decode(blob_b64))
        salt = base64.b64decode(blob["salt"])
        nonce = base64.b64decode(blob["nonce"])
        ct = base64.b64decode(blob["ct"])
        ekey = _derive_key(password, salt, blob["params"])
        plaintext = AESGCM(ekey).decrypt(nonce, ct, b"vault-export")
    except InvalidTag:
        raise VaultError("Incorrect export password or corrupted backup.")
    except Exception:
        raise VaultError("Could not read backup file.")
    data = json.loads(plaintext)
    n = 0
    for it in data.get("items", []):
        set_secret(conn, it["name"], it["value"], integration_id=it.get("integration_id"),
                   secret_type=it.get("secret_type", "api_key"), profile=it.get("profile", "local"))
        n += 1
    _audit(conn, "import", detail=f"restored {n} secret(s)")
    return n


# ── auto-unlock (opt-in convenience for an always-on local server) ────────
# Caches the derived key so the server can re-inject secrets on startup WITHOUT
# a password prompt — so previously-connected integrations auto-connect on boot.
# On Windows the key is wrapped with DPAPI (bound to the current user account),
# so copying the DB to another machine/user yields nothing. Off Windows it falls
# back to storing the raw key in the DB (no worse than the plaintext .env that
# already sits beside it). The unwrapped key is always re-verified against the
# vault verifier before use, so a corrupt/foreign blob can never set a bad key.
_AUTOUNLOCK_AAD = b"tobi-vault-autounlock-v1"


def _dpapi(data: bytes, *, unprotect: bool) -> Optional[bytes]:
    """Wrap/unwrap `data` with Windows DPAPI for the current user. Returns None
    when unavailable (non-Windows) or on any failure → caller falls back."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        def _mk(b: bytes):
            buf = ctypes.create_string_buffer(bytes(b), len(b))
            return _BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

        blob_in, _b1 = _mk(data)
        entropy, _b2 = _mk(_AUTOUNLOCK_AAD)   # keep buffers referenced until the call returns
        blob_out = _BLOB()
        crypt32 = ctypes.windll.crypt32
        fn = crypt32.CryptUnprotectData if unprotect else crypt32.CryptProtectData
        ok = fn(ctypes.byref(blob_in), None, ctypes.byref(entropy), None, None, 0, ctypes.byref(blob_out))
        if not ok:
            return None
        out = ctypes.string_at(blob_out.pbData, int(blob_out.cbData))
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return out
    except Exception:
        return None


def _ensure_autounlock_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS vault_autounlock ("
        "id INTEGER PRIMARY KEY CHECK (id=1), method TEXT, blob BLOB, created_at TEXT)"
    )


def enable_autounlock(conn: sqlite3.Connection) -> bool:
    """Persist the current (unlocked) key so the next server start auto-injects.
    Best-effort: returns False if locked or storage fails."""
    if _key is None:
        return False
    try:
        _ensure_autounlock_table(conn)
        wrapped = _dpapi(_key, unprotect=False)
        method = "dpapi" if wrapped else "raw"
        blob = wrapped if wrapped else _key
        conn.execute(
            "INSERT INTO vault_autounlock (id, method, blob, created_at) VALUES (1,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET method=excluded.method, blob=excluded.blob, created_at=excluded.created_at",
            (method, blob, _now()),
        )
        conn.commit()
        return True
    except Exception:
        return False


def disable_autounlock(conn: sqlite3.Connection) -> None:
    try:
        _ensure_autounlock_table(conn)
        conn.execute("DELETE FROM vault_autounlock")
        conn.commit()
    except Exception:
        pass


def autounlock_enabled(conn: sqlite3.Connection) -> bool:
    try:
        _ensure_autounlock_table(conn)
        return conn.execute("SELECT 1 FROM vault_autounlock WHERE id=1").fetchone() is not None
    except Exception:
        return False


def try_autounlock(conn: sqlite3.Connection) -> bool:
    """Startup path: if a cached key exists and verifies, load it + open a session
    so inject_env() can run with no password prompt. Returns True on success."""
    global _key
    if _key is not None:
        return True
    if not CRYPTO_AVAILABLE or not is_setup(conn):
        return False
    try:
        _ensure_autounlock_table(conn)
        row = conn.execute("SELECT method, blob FROM vault_autounlock WHERE id=1").fetchone()
    except Exception:
        return False
    if not row:
        return False
    method, blob = row[0], bytes(row[1])
    key = _dpapi(blob, unprotect=True) if method == "dpapi" else blob
    if not key or len(key) != _KEY_LEN:
        return False
    m = _meta(conn)
    if m is None or not _check_verifier(key, m["verifier"]):  # never trust an unverified key
        return False
    _key = key
    _new_session()
    _audit(conn, "autounlock", ok=True)
    return True


# ── status summary ──────────────────────────────────────────────────────
def status(conn: sqlite3.Connection) -> dict:
    prof = active_profile(conn)
    count = 0
    try:
        count = conn.execute("SELECT COUNT(*) FROM vault_secrets WHERE profile=?", (prof,)).fetchone()[0]
    except Exception:
        pass
    return {
        "crypto_available": CRYPTO_AVAILABLE,
        "setup": is_setup(conn),
        "unlocked": is_unlocked(),
        "active_profile": prof,
        "secret_count": count,
        "profiles": list_profiles(conn),
        "auto_lock_seconds": AUTO_LOCK_SECONDS,
        "autounlock": autounlock_enabled(conn),
    }
