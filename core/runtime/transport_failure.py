"""Why a model call never produced anything — classified once, worded once.

A provider call can fail two ways, and they need opposite reactions from the owner:

* the model answered, and the answer was unusable  → a different model may do better
* the call never reached a provider at all         → no model can help until it clears

Until this module existed only the first outcome had words. Every transport failure was
swallowed into an empty string by ``generate_step``, counted as malformed output, and
reported as "the current model is struggling — switch to a stronger model". On 2026-08-20
that cost the owner two #21 test runs against a Mission Control process that simply had no
outbound network: the model was fine, the picker could not have fixed anything, and the one
useful fact never surfaced.

Two rules hold everything here together:

1. **A code is bounded.** ``classify`` returns one of :data:`CODES` and never provider text,
   so nothing raw — a URL, a bearer token, a stack path, a provider error body — can ride an
   exception message into Chat, Runs, or the Telegram surface.
2. **The code and its wording live together.** A caller that has a code can always get the
   sentence, so the two cannot drift into disagreeing about what happened.
"""
from __future__ import annotations

from typing import Any, Optional

# Every code this module can return. `unknown` is the honest bucket: something failed before
# the model produced output and we could not say more than that.
CODES: tuple[str, ...] = ("unreachable", "timeout", "auth", "rate_limited", "provider_error", "unknown")

# Matched against the lowercased class names along the exception's MRO, in this order — the
# specific failures first, because most of them also inherit from a connection/OS error.
_MATCHERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("auth", ("authentication", "permissiondenied", "unauthorized", "forbidden", "notauthorized")),
    ("rate_limited", ("ratelimit", "toomanyrequests", "quotaexceeded")),
    ("timeout", ("timeout", "timedout", "deadlineexceeded")),
    ("unreachable", ("connection", "connecterror", "gaierror", "unreachable", "socket",
                     "ssl", "proxyerror", "nameresolution", "dns")),
    ("provider_error", ("internalserver", "serviceunavailable", "badgateway", "apistatus",
                        "apiresponse", "servererror")),
)

_STATUS_CODES: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("auth", (401, 403)),
    ("rate_limited", (429,)),
)

_MESSAGES: dict[str, str] = {
    "unreachable": (
        "I never reached the model, sir — the connection to the provider could not be opened. "
        "Nothing is wrong with the model itself, so a different one will not help until this "
        "machine can reach the internet again."
    ),
    "timeout": (
        "I never reached the model, sir — the provider did not answer in time. "
        "Do give it a moment and send that again."
    ),
    "auth": (
        "I never reached the model, sir — the provider refused our credentials. "
        "Do check that provider's key in Integrations; a different model on the same key "
        "will be refused too."
    ),
    "rate_limited": (
        "I never reached the model, sir — the provider is rate-limiting us just now. "
        "Do give it a minute and send that again."
    ),
    "provider_error": (
        "I never reached the model, sir — the provider itself returned an error before "
        "answering. That is on their side; do try again shortly."
    ),
    "unknown": (
        "I never reached the model, sir — the call failed before the model produced anything. "
        "Switching models will not help on its own; the connection to the provider is what "
        "needs looking at."
    ),
}


def classify(exc: BaseException) -> str:
    """Return one bounded code in :data:`CODES` for a failed provider call.

    Never returns provider text. An exception nobody anticipated still classifies, as
    ``unknown`` — a failure with no word for it is exactly how this one hid for so long.
    """
    status = _status_of(exc)
    if status is not None:
        for code, values in _STATUS_CODES:
            if status in values:
                return code
        if status >= 500:
            return "provider_error"
    names = " ".join(cls.__name__.lower() for cls in type(exc).__mro__)
    for code, needles in _MATCHERS:
        if any(needle in names for needle in needles):
            return code
    return "unknown"


def owner_message(code: Optional[str]) -> str:
    """The owner-facing sentence for a code. Unknown codes fall back to the honest bucket."""
    return _MESSAGES.get(code or "", _MESSAGES["unknown"])


def _status_of(exc: BaseException) -> Optional[int]:
    """HTTP status carried by SDK errors, when there is one."""
    for attribute in ("status_code", "status", "http_status"):
        value: Any = getattr(exc, attribute, None)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def record(client: Any, exc: Optional[BaseException]) -> Optional[str]:
    """Stamp the outcome of one provider call on the client, the way usage already is.

    Returns the code so a caller can act on it immediately. Passing ``None`` clears the
    stamp, which every call must do before it starts: a stale failure from the previous
    step would otherwise describe this one.
    """
    code = classify(exc) if exc is not None else None
    try:
        client.last_transport_error = code
    except Exception:  # noqa: BLE001 - a client that refuses attributes must not break a turn
        pass
    return code


def last(client: Any) -> Optional[str]:
    """The code stamped by the client's most recent call, if it failed to reach a provider."""
    code = getattr(client, "last_transport_error", None)
    return code if code in CODES else None
