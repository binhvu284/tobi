"""Repository-scoped GitHub App adapter for coding workflows."""
from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from core.coding_policy import CodingPolicy, PolicyDenied


class GitHubCodingError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


_PEM_RE = re.compile(
    r"-{2,}\s*BEGIN\s+(?P<label>[A-Z ]+?)\s*-{2,}(?P<body>.*?)-{2,}\s*END\s+(?P=label)\s*-{2,}",
    re.DOTALL,
)


def normalize_private_key(raw: str) -> str:
    """Rebuild a PEM that lost its line structure on the way in.

    The Coding App private key is entered in a single-line password field, and a `.pem` is
    inherently multi-line. Depending on the browser, pasting one can arrive with its newlines
    stripped, turned into spaces, or escaped as a literal backslash-n -- and an owner may
    reasonably paste it wrapped in quotes. None of those are the owner making a mistake, so
    none of them should read as "your key is invalid".

    Reconstructs the canonical form from the base64 body: strip the wrapper, drop every
    whitespace character, re-wrap at 64 columns. A value that carries no PEM envelope at all
    is returned untouched, so the caller's error can say so rather than mangling it further.
    """
    text = (raw or "").strip()
    if text[:1] in {'"', "'"} and text[-1:] == text[:1] and len(text) > 1:
        text = text[1:-1].strip()
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n")
    match = _PEM_RE.search(text)
    if not match:
        return text
    label = " ".join(match.group("label").split())
    body = "".join(match.group("body").split())
    lines = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN {label}-----\n{lines}\n-----END {label}-----\n"


def describe_private_key(raw: str) -> str:
    """Say what shape a rejected key has, without ever revealing the key.

    Only structural facts: length, whether the PEM envelope is present, and which label it
    carries. That is enough to separate the three things owners actually hit -- pasting the
    Client ID instead of the key, pasting only part of the file, and an encrypted key.
    """
    text = (raw or "").strip()
    if not text:
        return "the field is empty"
    match = _PEM_RE.search(text.replace("\\n", "\n"))
    if not match:
        head = "-----BEGIN" in text
        return (f"{len(text)} characters with a BEGIN line but no matching END line -- "
                "the paste looks truncated" if head else
                f"{len(text)} characters with no -----BEGIN/-----END envelope -- "
                "this does not look like the .pem file (the Client ID is not the private key)")
    label = " ".join(match.group("label").split())
    body = "".join(match.group("body").split())
    if "ENCRYPTED" in label:
        return f"a passphrase-protected key ({label}) -- GitHub App keys must not be encrypted"
    return f"a {label} block with {len(body)} base64 characters"


@dataclass
class InstallationToken:
    value: str
    expires_at: float


class GitHubCodingService:
    API = "https://api.github.com"

    def __init__(self, policy: CodingPolicy, repository: str | None = None) -> None:
        self.policy = policy
        self.repository = repository or os.getenv("TOBI_GITHUB_REPOSITORY", "binhvu284/tobi")
        allowed = str(policy.data.get("repository", {}).get("allowed_repository", "")).strip().lower()
        if allowed and allowed != self.repository.lower():
            raise PolicyDenied("GitHub App repository does not match the repository allowed by coding policy.")
        self.app_id = os.getenv("GITHUB_APP_ID", "")
        self.installation_id = os.getenv("GITHUB_APP_INSTALLATION_ID", "")
        self.private_key = normalize_private_key(os.getenv("GITHUB_APP_PRIVATE_KEY", ""))
        self._token: InstallationToken | None = None

    def configured(self) -> bool:
        return bool(self.app_id and self.installation_id and self.private_key)

    def test(self) -> bool:
        """Validate GitHub App credentials without enabling coding mutations."""
        return bool(self._installation_token())

    def _jwt(self) -> str:
        if not self.configured():
            raise GitHubCodingError("GitHub App credentials are not configured in the vault.")
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as exc:
            raise GitHubCodingError("cryptography is required for GitHub App authentication.") from exc
        now = int(time.time())
        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        payload = _b64url(json.dumps({"iat": now - 30, "exp": now + 540, "iss": self.app_id},
                                     separators=(",", ":")).encode())
        signing_input = f"{header}.{payload}".encode("ascii")
        try:
            key = serialization.load_pem_private_key(self.private_key.encode("utf-8"), password=None)
            signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        except Exception as exc:
            raise GitHubCodingError(
                f"GitHub App private key is invalid: the field holds "
                f"{describe_private_key(os.getenv('GITHUB_APP_PRIVATE_KEY', ''))}. "
                f"Paste the whole downloaded .pem, including its BEGIN and END lines."
            ) from exc
        return f"{header}.{payload}.{_b64url(signature)}"

    def _installation_token(self) -> str:
        if self._token and self._token.expires_at > time.time() + 60:
            return self._token.value
        # Both ids are numeric. The App page shows an "App ID", a "Client ID" (Iv23...) and a
        # "Client secret" next to each other, and the installation id lives on a different
        # page entirely -- so pasting the wrong one is the ordinary mistake, not the unusual
        # one. Caught here it names the field; left to GitHub it returns an opaque 404.
        for label, value, where in (
            ("Coding App ID", self.app_id, "the App ID on the app's settings page"),
            ("Coding App installation ID", self.installation_id,
             "the number at the end of the /settings/installations/<id> URL"),
        ):
            if not value.strip().isdigit():
                raise GitHubCodingError(
                    f"{label} must be the numeric id -- it currently holds "
                    f"{len(value.strip())} characters that are not all digits. Use {where}. "
                    "The Client ID (Iv23...) is a different value and will not work here."
                )
        response = requests.post(
            f"{self.API}/app/installations/{self.installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {self._jwt()}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"}, timeout=20,
        )
        if response.status_code not in (200, 201):
            raise GitHubCodingError(f"GitHub App token request failed with HTTP {response.status_code}.")
        body = response.json()
        token = str(body.get("token", ""))
        if not token:
            raise GitHubCodingError("GitHub App returned no installation token.")
        self._token = InstallationToken(token, time.time() + 3000)
        return token

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.policy.feature_enabled("github"):
            raise PolicyDenied("GitHub coding capability is disabled by policy.")
        response = None
        for attempt in range(3):
            response = requests.request(
                method, f"{self.API}{path}",
                headers={"Authorization": f"Bearer {self._installation_token()}",
                         "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
                timeout=20, **kwargs,
            )
            if response.status_code == 401 and attempt == 0:
                self._token = None
                continue
            if response.status_code in {429, 502, 503, 504} and attempt < 2:
                delay = min(float(response.headers.get("Retry-After", "1") or 1), 5.0)
                time.sleep(max(0.2, delay))
                continue
            break
        assert response is not None
        if response.status_code >= 400:
            raise GitHubCodingError(f"GitHub operation failed with HTTP {response.status_code}.",
                                    status_code=response.status_code)
        return response.json() if response.content else {}

    def create_draft_pr(self, branch: str, title: str, body: str, base: str = "main") -> dict[str, Any]:
        existing = self.find_open_pr(branch, base=base)
        if existing:
            return {**existing, "existing": True}
        try:
            data = self._request("POST", f"/repos/{self.repository}/pulls", json={
                "title": title[:240], "head": branch, "base": base, "body": body[:60_000], "draft": True,
            })
        except GitHubCodingError as exc:
            if exc.status_code == 422:
                existing = self.find_open_pr(branch, base=base)
                if existing:
                    return {**existing, "existing": True}
            raise
        return {"number": data.get("number"), "url": data.get("html_url"), "head_sha": data.get("head", {}).get("sha"),
                "base_sha": data.get("base", {}).get("sha"), "draft": bool(data.get("draft", True))}

    def find_open_pr(self, branch: str, base: str = "main") -> dict[str, Any] | None:
        owner = self.repository.split("/", 1)[0]
        data = self._request(
            "GET", f"/repos/{self.repository}/pulls",
            params={"state": "open", "head": f"{owner}:{branch}", "base": base, "per_page": 10},
        )
        rows = data if isinstance(data, list) else []
        if not rows:
            return None
        item = rows[0]
        return {"number": item.get("number"), "url": item.get("html_url"),
                "head_sha": item.get("head", {}).get("sha"), "base_sha": item.get("base", {}).get("sha"),
                "draft": bool(item.get("draft", True))}

    def get_pr(self, number: int) -> dict[str, Any]:
        data = self._request("GET", f"/repos/{self.repository}/pulls/{number}")
        return {"number": data.get("number"), "url": data.get("html_url"), "state": data.get("state"),
                "draft": data.get("draft"), "mergeable": data.get("mergeable"),
                "mergeable_state": data.get("mergeable_state"), "head_sha": data.get("head", {}).get("sha"),
                "base_sha": data.get("base", {}).get("sha"), "merged": bool(data.get("merged")),
                "merged_at": data.get("merged_at"), "merge_commit_sha": data.get("merge_commit_sha")}

    def merge_readiness(self, number: int) -> dict[str, Any]:
        pr = self.get_pr(number)
        checks = self._request("GET", f"/repos/{self.repository}/commits/{pr['head_sha']}/check-runs")
        runs = checks.get("check_runs", []) if isinstance(checks, dict) else []
        pending = [run.get("name") for run in runs if run.get("status") != "completed"]
        failed = [run.get("name") for run in runs if run.get("status") == "completed" and run.get("conclusion") not in {"success", "neutral", "skipped"}]
        statuses = self._request("GET", f"/repos/{self.repository}/commits/{pr['head_sha']}/status")
        state = statuses.get("state") if isinstance(statuses, dict) else None
        status_contexts = statuses.get("statuses", []) if isinstance(statuses, dict) else []
        # GitHub reports combined state "pending" when a commit has no status contexts.
        # That means no checks are configured, not that a check is still running.
        status_failed = bool(status_contexts) and state in {"failure", "error"}
        status_pending = bool(status_contexts) and state == "pending"
        ready = bool(pr.get("mergeable") is True and pr.get("mergeable_state") not in {"dirty", "blocked"}
                     and not pending and not failed and not status_failed and not status_pending)
        if status_failed:
            failed.append("commit status")
        if status_pending:
            pending.append("commit status")
        return {"ready": ready, "pull_request": pr, "pending_checks": pending, "failed_checks": failed}

    def mark_ready(self, number: int) -> None:
        query = "mutation($id:ID!){markPullRequestReadyForReview(input:{pullRequestId:$id}){pullRequest{isDraft}}}"
        pr = self._request("GET", f"/repos/{self.repository}/pulls/{number}")
        node_id = pr.get("node_id")
        if not node_id:
            raise GitHubCodingError("GitHub PR has no GraphQL node id.")
        self._request("POST", "/graphql", json={"query": query, "variables": {"id": node_id}})

    def squash_merge(self, number: int, expected_head_sha: str, title: str) -> dict[str, Any]:
        if not self.policy.feature_enabled("merge"):
            raise PolicyDenied("Merge capability is disabled by policy.")
        data = self._request("PUT", f"/repos/{self.repository}/pulls/{number}/merge", json={
            "commit_title": title[:240], "merge_method": "squash", "sha": expected_head_sha,
        })
        if not data.get("merged"):
            raise GitHubCodingError("GitHub did not merge the pull request.")
        return {"merged": True, "sha": data.get("sha"), "message": data.get("message")}

    def create_annotated_tag(self, version: str, commit_sha: str, message: str) -> dict[str, Any]:
        tag_name = f"v{version}"
        try:
            existing = self._request("GET", f"/repos/{self.repository}/git/ref/tags/{tag_name}")
            if existing.get("ref"):
                obj = existing.get("object", {})
                target_sha = obj.get("sha")
                if obj.get("type") == "tag" and target_sha:
                    tag_object = self._request("GET", f"/repos/{self.repository}/git/tags/{target_sha}")
                    target_sha = tag_object.get("object", {}).get("sha")
                if target_sha != commit_sha:
                    raise GitHubCodingError(f"Existing tag {tag_name} points to a different commit.")
                return {"tag": tag_name, "ref": existing.get("ref"),
                        "tag_sha": existing.get("object", {}).get("sha"), "existing": True}
        except GitHubCodingError as exc:
            if exc.status_code != 404:
                raise
        tag = self._request("POST", f"/repos/{self.repository}/git/tags", json={
            "tag": tag_name, "message": message[:10_000], "object": commit_sha, "type": "commit",
        })
        tagged_sha = tag.get("sha")
        if not tagged_sha:
            raise GitHubCodingError("GitHub did not create the annotated tag object.")
        ref = self._request("POST", f"/repos/{self.repository}/git/refs", json={
            "ref": f"refs/tags/{tag_name}", "sha": tagged_sha,
        })
        return {"tag": tag_name, "ref": ref.get("ref"), "tag_sha": tagged_sha}
