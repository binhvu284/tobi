"""Repository-scoped GitHub App adapter for coding workflows."""
from __future__ import annotations

import base64
import json
import os
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


@dataclass
class InstallationToken:
    value: str
    expires_at: float


class GitHubCodingService:
    API = "https://api.github.com"

    def __init__(self, policy: CodingPolicy, repository: str | None = None) -> None:
        self.policy = policy
        self.repository = repository or os.getenv("TOBI_GITHUB_REPOSITORY", "binhvu284/tobi")
        allowed = str(policy.data.get("repository", {}).get("allowed_remote_suffix", "")).lower().removesuffix(".git")
        if "/" in allowed and not allowed.endswith(self.repository.lower()):
            raise PolicyDenied("GitHub App repository does not match the repository allowed by coding policy.")
        self.app_id = os.getenv("GITHUB_APP_ID", "")
        self.installation_id = os.getenv("GITHUB_APP_INSTALLATION_ID", "")
        self.private_key = os.getenv("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n")
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
            raise GitHubCodingError("GitHub App private key is invalid.") from exc
        return f"{header}.{payload}.{_b64url(signature)}"

    def _installation_token(self) -> str:
        if self._token and self._token.expires_at > time.time() + 60:
            return self._token.value
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
        response = requests.request(
            method, f"{self.API}{path}",
            headers={"Authorization": f"Bearer {self._installation_token()}",
                     "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            timeout=20, **kwargs,
        )
        if response.status_code >= 400:
            raise GitHubCodingError(f"GitHub operation failed with HTTP {response.status_code}.",
                                    status_code=response.status_code)
        return response.json() if response.content else {}

    def create_draft_pr(self, branch: str, title: str, body: str, base: str = "main") -> dict[str, Any]:
        data = self._request("POST", f"/repos/{self.repository}/pulls", json={
            "title": title[:240], "head": branch, "base": base, "body": body[:60_000], "draft": True,
        })
        return {"number": data.get("number"), "url": data.get("html_url"), "head_sha": data.get("head", {}).get("sha"),
                "base_sha": data.get("base", {}).get("sha"), "draft": bool(data.get("draft", True))}

    def get_pr(self, number: int) -> dict[str, Any]:
        data = self._request("GET", f"/repos/{self.repository}/pulls/{number}")
        return {"number": data.get("number"), "url": data.get("html_url"), "state": data.get("state"),
                "draft": data.get("draft"), "mergeable": data.get("mergeable"),
                "mergeable_state": data.get("mergeable_state"), "head_sha": data.get("head", {}).get("sha"),
                "base_sha": data.get("base", {}).get("sha"), "merged": bool(data.get("merged")),
                "merge_commit_sha": data.get("merge_commit_sha")}

    def merge_readiness(self, number: int) -> dict[str, Any]:
        pr = self.get_pr(number)
        checks = self._request("GET", f"/repos/{self.repository}/commits/{pr['head_sha']}/check-runs")
        runs = checks.get("check_runs", []) if isinstance(checks, dict) else []
        pending = [run.get("name") for run in runs if run.get("status") != "completed"]
        failed = [run.get("name") for run in runs if run.get("status") == "completed" and run.get("conclusion") not in {"success", "neutral", "skipped"}]
        ready = bool(pr.get("mergeable") is True and pr.get("mergeable_state") not in {"dirty", "blocked"}
                     and not pending and not failed)
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
