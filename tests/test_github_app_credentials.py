"""The Coding App credentials must survive the form they are entered through.

A GitHub App private key is a multi-line `.pem`. Mission Control collects it in a single-line
password field, so what arrives depends on the browser: newlines stripped, newlines turned into
spaces, newlines escaped as literal backslash-n, or the whole thing wrapped in quotes because
the owner copied it out of a config snippet. None of those is the owner getting it wrong, and
none of them should be reported as "your key is invalid" -- which is what happened: three
correct credentials could not be saved, and Update looked like a dead button.

The ids have their own trap. The app's settings page shows "App ID", "Client ID" (`Iv23...`)
and "Client secret" together, while the *installation* id lives on a different page. Pasting
the Client ID is the ordinary mistake. GitHub answers an opaque 404 for it, so the check has to
happen here where the field can be named.

Nothing in this file ever prints key material -- the diagnostics are structural only.
"""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from core.github_coding import (  # noqa: E402
    GitHubCodingError, GitHubCodingService, describe_private_key, normalize_private_key,
)

FAILURES: list[str] = []
NL = "\n"


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'} {label}{('  -> ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


def loads(pem: str) -> bool:
    try:
        serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
        return True
    except Exception:
        return False


key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = key.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
    serialization.NoEncryption(),
).decode()

# --- every way a single-line field can mangle a PEM --------------------------------------
for label, raw in [
    ("an untouched .pem", PEM),
    ("newlines stripped by the input", PEM.replace(NL, "")),
    ("newlines collapsed to spaces", PEM.replace(NL, " ")),
    ("newlines escaped as backslash-n", PEM.replace(NL, "\\n")),
    ("pasted wrapped in double quotes", f'"{PEM}"'),
    ("pasted wrapped in single quotes", f"'{PEM}'"),
    ("surrounded by stray whitespace", f"   {PEM}   "),
    ("CRLF line endings", PEM.replace(NL, "\r\n")),
]:
    ok(f"{label} normalizes to a loadable key", loads(normalize_private_key(raw)))

ok("normalizing is idempotent", normalize_private_key(normalize_private_key(PEM)) ==
   normalize_private_key(PEM))
ok("the normalized form keeps its envelope",
   normalize_private_key(PEM.replace(NL, "")).startswith("-----BEGIN RSA PRIVATE KEY-----" + NL))
ok("the body is re-wrapped, not left as one long line",
   max(len(line) for line in normalize_private_key(PEM.replace(NL, "")).splitlines()) <= 64)

# --- a value that is not a key is described, never mangled into one -----------------------
ok("a value with no PEM envelope is returned untouched",
   normalize_private_key("Iv23liABCDEFGHIJKLMN") == "Iv23liABCDEFGHIJKLMN")
ok("pasting the Client ID is named as such",
   "Client ID is not the private key" in describe_private_key("Iv23liABCDEFGHIJKLMN"))
ok("a truncated paste is named as truncated",
   "truncated" in describe_private_key("-----BEGIN RSA PRIVATE KEY-----" + NL + "MIIEow"))
ok("an empty field is named as empty", describe_private_key("") == "the field is empty")
ok("an encrypted key is named as encrypted",
   "must not be encrypted" in describe_private_key(
       "-----BEGIN ENCRYPTED PRIVATE KEY-----" + NL + "AAAA" + NL + "-----END ENCRYPTED PRIVATE KEY-----"))

# The diagnostic must never echo the secret back into a log or a toast.
body = "".join(PEM.splitlines()[1:-1])
described = describe_private_key(PEM)
ok("the description never contains key material", body[:40] not in described, described)
ok("the description is structural", "base64 characters" in described, described)


# --- the ids must be numeric, and the failure must name the field ------------------------
class _Policy:
    data = {"repository": {"allowed_repository": "binhvu284/tobi"}, "capabilities": {"github": True}}
    hash = "test"

    def feature_enabled(self, _name: str) -> bool:
        return True


def token_error(app_id: str, installation_id: str, monkey: dict) -> str:
    import os
    saved = {k: os.environ.get(k) for k in monkey}
    try:
        os.environ.update(monkey)
        os.environ["GITHUB_APP_ID"] = app_id
        os.environ["GITHUB_APP_INSTALLATION_ID"] = installation_id
        service = GitHubCodingService(_Policy(), repository="binhvu284/tobi")
        try:
            service._installation_token()
            return ""
        except GitHubCodingError as exc:
            return str(exc)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


env = {"GITHUB_APP_PRIVATE_KEY": PEM}
client_id_mistake = token_error("4413900", "Iv23liABCDEFGHIJKLMN", env)
ok("a non-numeric installation id is refused before any request",
   "installation ID must be the numeric id" in client_id_mistake, client_id_mistake)
ok("and it says where the real one lives",
   "/settings/installations/" in client_id_mistake, client_id_mistake)
ok("and it warns about the Client ID specifically",
   "Iv23" in client_id_mistake, client_id_mistake)

app_id_mistake = token_error("Iv23liABCDEFGHIJKLMN", "87654321", env)
ok("a non-numeric app id is refused too",
   "App ID must be the numeric id" in app_id_mistake, app_id_mistake)

ok("two good numeric ids get past the shape check",
   "must be the numeric id" not in token_error("4413900", "87654321", env))

print(f"\n{'ALL' if not FAILURES else str(len(FAILURES)) + ' OF'} "
      f"{'GITHUB APP CREDENTIAL CHECKS PASSED' if not FAILURES else 'CHECKS FAILED: ' + ', '.join(FAILURES)}")
raise SystemExit(1 if FAILURES else 0)
