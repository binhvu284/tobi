# Mission Control V2 Threat Model

This is the local, synthetic security gate for Queue item #21 T12. It performs no live attack,
remote request, credential use, dependency installation, or deployment.

| Threat | Asset | Entry point | Trust boundary | Unsafe failure | Control owner | Evidence |
|---|---|---|---|---|---|---|
| Prompt injection | Owner intent and safety rules | Brain or retrieved content | Untrusted content to Runtime context | Content gains route, tool, or instruction authority | `core.runtime.owner_intelligence` | `tests/test_mc_runtime_security.py` |
| Secret leakage | Credentials and private values | Event and trace payloads | Runtime input to durable SQLite history | A secret marker reaches persisted JSON | `core.runtime.event_store` | `tests/test_mc_runtime_security.py` |
| Authority over-reach | Tool permissions | Policy facts | Caller claims to central policy decision | Untrusted authority permits a tool | `core.runtime.policy` | `tests/test_mc_runtime_security.py` |
| Budget exhaustion | Bounded local resources | Owner and plan limits | Requested budget to loop controller | A higher override wins or exhausted work continues | `core.runtime.budget` | `tests/test_mc_runtime_security.py` |
| Network SSRF | Local network and metadata services | Tool-driven URL | Untrusted URL to outbound request | Private, local, metadata, or non-HTTP destination is reachable | `core.net_guard` | `tests/test_mc_runtime_security.py` |
| Path traversal | Repository and host filesystem | Coding file path | Worker path to coding policy | A resolved path escapes the approved repository | `core.coding_policy` | `tests/test_mc_runtime_security.py` |
| Supply chain | Canonical tool contracts | Tool schema metadata | Remote metadata to canonical registry | A remote schema enters the trusted catalog | `core.runtime.tool_registry` | `tests/test_mc_runtime_security.py` |
| Recovery | Fail-closed run state | Boundary error or missing proof | Failed control to activation gate | Missing or failed evidence still permits release or autonomy | `core.runtime.security` | `tests/test_mc_runtime_security.py` |

Every row must produce a sanitized evidence reference. Missing, duplicate, unknown, failed, or
unsanitized probes block the T11 release and autonomy gates.
