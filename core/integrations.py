"""Integrations - Tobi Agent
External service connectors. Each has is_available() and test().
"""
from core.env_utils import safe_load_dotenv
safe_load_dotenv()

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class NotionIntegration:
    def __init__(self):
        self.api_key = os.getenv("NOTION_API_KEY", "")
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

    def is_available(self) -> bool:
        return bool(self.api_key)

    def test(self) -> bool:
        if not self.is_available():
            return False
        try:
            import requests
            r = requests.get(f"{self.base_url}/users/me", headers=self.headers, timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    def search_pages(self, query: str) -> list:
        if not self.is_available():
            return []
        try:
            import requests
            r = requests.post(
                f"{self.base_url}/search",
                headers=self.headers,
                json={"query": query, "filter": {"value": "page", "property": "object"}},
                timeout=10,
            )
            return r.json().get("results", [])
        except Exception as e:
            logger.warning(f"Notion search error: {e}")
            return []

    def create_page(self, title: str, content: str, parent_id: str) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            import requests
            r = requests.post(
                f"{self.base_url}/pages",
                headers=self.headers,
                json={
                    "parent": {"page_id": parent_id},
                    "properties": {"title": {"title": [{"text": {"content": title}}]}},
                    "children": [{"object": "block", "type": "paragraph",
                                  "paragraph": {"rich_text": [{"text": {"content": content}}]}}],
                },
                timeout=10,
            )
            return r.json().get("id")
        except Exception as e:
            logger.warning(f"Notion create page error: {e}")
            return None

    def append_to_page(self, page_id: str, content: str) -> bool:
        if not self.is_available():
            return False
        try:
            import requests
            r = requests.patch(
                f"{self.base_url}/blocks/{page_id}/children",
                headers=self.headers,
                json={"children": [{"object": "block", "type": "paragraph",
                                    "paragraph": {"rich_text": [{"text": {"content": content}}]}}]},
                timeout=10,
            )
            return r.status_code == 200
        except Exception as e:
            logger.warning(f"Notion append error: {e}")
            return False

    def get_page_content(self, page_id: str) -> str:
        """Read a page's block children as plain text (paragraphs, headings, list items,
        to-dos). Best-effort; returns '' on any failure. Lets the Conductor ground a
        Notion → project → tasks chain in the page's real content."""
        if not self.is_available():
            return ""
        try:
            import requests
            pid = (page_id or "").replace("-", "")
            r = requests.get(
                f"{self.base_url}/blocks/{pid}/children",
                headers=self.headers, params={"page_size": 100}, timeout=10,
            )
            if r.status_code != 200:
                return ""
            lines = []
            for b in r.json().get("results", []):
                t = b.get("type")
                node = b.get(t, {}) if isinstance(b.get(t), dict) else {}
                rich = node.get("rich_text", [])
                text = "".join(rt.get("plain_text", "") for rt in rich).strip()
                if not text:
                    continue
                if t in ("to_do",):
                    lines.append(f"[{'x' if node.get('checked') else ' '}] {text}")
                elif t in ("bulleted_list_item", "numbered_list_item"):
                    lines.append(f"- {text}")
                elif t and t.startswith("heading"):
                    lines.append(f"# {text}")
                else:
                    lines.append(text)
            return "\n".join(lines)[:4000]
        except Exception as e:
            logger.warning(f"Notion read page error: {e}")
            return ""


class GitHubIntegration:
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN", "")
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def is_available(self) -> bool:
        return bool(self.token)

    def test(self) -> bool:
        if not self.is_available():
            return False
        try:
            import requests
            r = requests.get(f"{self.base_url}/user", headers=self.headers, timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    # ── repo listing ───────────────────────────────────────────

    def list_repos(self, limit: int = 30, sort: str = "updated",
                   visibility: str = "all", affiliation: str = "owner,collaborator,organization_member") -> list:
        """List repositories accessible to the authenticated user.
        sort: created | updated | pushed | full_name
        visibility: all | public | private
        affiliation: comma-separated owner,collaborator,organization_member
        """
        if not self.is_available():
            return []
        try:
            import requests
            r = requests.get(
                f"{self.base_url}/user/repos",
                headers=self.headers,
                params={"per_page": min(limit, 100), "sort": sort,
                        "visibility": visibility, "affiliation": affiliation},
                timeout=15,
            )
            if r.status_code != 200:
                logger.warning(f"GitHub list_repos HTTP {r.status_code}: {r.text[:200]}")
                return []
            return r.json()
        except Exception as e:
            logger.warning(f"GitHub list_repos error: {e}")
            return []

    def list_org_repos(self, org: str, limit: int = 30, type_: str = "all") -> list:
        """List repositories for an organization.
        type_: all | public | private | forks | sources, member-internal
        """
        if not self.is_available():
            return []
        try:
            import requests
            r = requests.get(
                f"{self.base_url}/orgs/{org}/repos",
                headers=self.headers,
                params={"per_page": min(limit, 100), "type": type_},
                timeout=15,
            )
            if r.status_code != 200:
                logger.warning(f"GitHub list_org_repos HTTP {r.status_code}: {r.text[:200]}")
                return []
            return r.json()
        except Exception as e:
            logger.warning(f"GitHub list_org_repos error: {e}")
            return []

    # ── repo reading ───────────────────────────────────────────

    def get_repo_info(self, repo: str) -> dict:
        if not self.is_available():
            return {}
        try:
            import requests
            r = requests.get(f"{self.base_url}/repos/{repo}", headers=self.headers, timeout=10)
            if r.status_code != 200:
                logger.warning(f"GitHub get_repo HTTP {r.status_code} for {repo}")
                return {}
            return r.json()
        except Exception as e:
            logger.warning(f"GitHub get_repo error: {e}")
            return {}

    def get_readme(self, repo: str) -> str:
        """Fetch the rendered README of a repo as plain text."""
        if not self.is_available():
            return ""
        try:
            import requests
            r = requests.get(
                f"{self.base_url}/repos/{repo}/readme",
                headers={**self.headers, "Accept": "application/vnd.github.raw+json"},
                timeout=10,
            )
            if r.status_code != 200:
                return ""
            return r.text[:8000]
        except Exception as e:
            logger.warning(f"GitHub get_readme error: {e}")
            return ""

    def get_file_contents(self, repo: str, path: str = "", ref: str = "") -> list | dict:
        """List directory contents or read a single file.
        Returns a list of entries for directories, or a dict with 'content'/'encoding' for files.
        path: file or directory path within the repo (empty = root).
        ref: optional branch/tag/commit.
        """
        if not self.is_available():
            return []
        try:
            import requests
            url = f"{self.base_url}/repos/{repo}/contents/{path}" if path else f"{self.base_url}/repos/{repo}/contents"
            params = {}
            if ref:
                params["ref"] = ref
            r = requests.get(url, headers=self.headers, params=params or None, timeout=10)
            if r.status_code != 200:
                logger.warning(f"GitHub get_file_contents HTTP {r.status_code} for {repo}/{path}")
                return []
            data = r.json()
            # Decode file content from base64
            if isinstance(data, dict) and data.get("encoding") == "base64":
                import base64
                try:
                    raw = base64.b64decode(data.get("content", ""))
                    data["decoded_content"] = raw.decode("utf-8", errors="replace")[:16000]
                except Exception:
                    pass
            return data
        except Exception as e:
            logger.warning(f"GitHub get_file_contents error: {e}")
            return []

    def list_branches(self, repo: str, limit: int = 20) -> list:
        if not self.is_available():
            return []
        try:
            import requests
            r = requests.get(
                f"{self.base_url}/repos/{repo}/branches",
                headers=self.headers,
                params={"per_page": min(limit, 100)},
                timeout=10,
            )
            return r.json() if r.status_code == 200 else []
        except Exception as e:
            logger.warning(f"GitHub list_branches error: {e}")
            return []

    def get_tree(self, repo: str, branch: str = "", recursive: bool = True) -> list:
        """Get the full file tree of a repo. Returns a flat list of path entries."""
        if not self.is_available():
            return []
        try:
            import requests
            sha = branch or "HEAD"
            r = requests.get(
                f"{self.base_url}/repos/{repo}/git/trees/{sha}",
                headers=self.headers,
                params={"recursive": "1"} if recursive else None,
                timeout=15,
            )
            if r.status_code != 200:
                logger.warning(f"GitHub get_tree HTTP {r.status_code} for {repo}")
                return []
            tree = r.json().get("tree", [])
            # Handle truncated trees
            if r.json().get("truncated"):
                logger.warning(f"GitHub tree for {repo} is truncated (>100k entries)")
            return tree
        except Exception as e:
            logger.warning(f"GitHub get_tree error: {e}")
            return []

    # ── issues & commits ───────────────────────────────────────

    def list_issues(self, repo: str, limit: int = 5, state: str = "open") -> list:
        if not self.is_available():
            return []
        try:
            import requests
            r = requests.get(
                f"{self.base_url}/repos/{repo}/issues",
                headers=self.headers,
                params={"per_page": limit, "state": state},
                timeout=10,
            )
            if r.status_code != 200:
                return []
            # Filter out pull requests (GitHub's /issues endpoint includes PRs)
            return [i for i in r.json() if "pull_request" not in i]
        except Exception as e:
            logger.warning(f"GitHub list_issues error: {e}")
            return []

    def create_issue(self, repo: str, title: str, body: str) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            import requests
            r = requests.post(
                f"{self.base_url}/repos/{repo}/issues",
                headers=self.headers,
                json={"title": title, "body": body},
                timeout=10,
            )
            if r.status_code == 201:
                return r.json().get("html_url")
            logger.warning(f"GitHub create_issue HTTP {r.status_code}: {r.text[:200]}")
            return None
        except Exception as e:
            logger.warning(f"GitHub create_issue error: {e}")
            return None

    def get_recent_commits(self, repo: str, limit: int = 5, branch: str = "") -> list:
        if not self.is_available():
            return []
        try:
            import requests
            params: dict = {"per_page": limit}
            if branch:
                params["sha"] = branch
            r = requests.get(
                f"{self.base_url}/repos/{repo}/commits",
                headers=self.headers,
                params=params,
                timeout=10,
            )
            return r.json() if r.status_code == 200 else []
        except Exception as e:
            logger.warning(f"GitHub get_commits error: {e}")
            return []

    def list_pulls(self, repo: str, limit: int = 5, state: str = "open") -> list:
        if not self.is_available():
            return []
        try:
            import requests
            r = requests.get(
                f"{self.base_url}/repos/{repo}/pulls",
                headers=self.headers,
                params={"per_page": limit, "state": state},
                timeout=10,
            )
            return r.json() if r.status_code == 200 else []
        except Exception as e:
            logger.warning(f"GitHub list_pulls error: {e}")
            return []


class GoogleIntegration:
    """Google Workspace connector — OAuth2 flow for Drive, Gmail, Calendar.

    Setup steps (one-time):
      1. Go to https://console.cloud.google.com/apis/credentials
      2. Create an OAuth 2.0 Client ID (type: Web application)
      3. Add the redirect URI shown in the Integrations page to "Authorized redirect URIs"
      4. Enable the Drive, Gmail, and Calendar APIs:
         https://console.cloud.google.com/apis/library/drive.googleapis.com
         https://console.cloud.google.com/apis/library/gmail.googleapis.com
         https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
      5. Paste the client ID and secret into the Integrations page or .env
      6. Click "Connect with Google" to start the OAuth consent flow
    """

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    REVOKE_URL = "https://oauth2.googleapis.com/revoke"

    SCOPES = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
    ]

    def __init__(self):
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        dashboard_port = os.getenv("DASHBOARD_PORT", "8080")
        self.redirect_uri = os.getenv(
            "GOOGLE_REDIRECT_URI",
            f"http://localhost:{dashboard_port}/api/integrations/google/oauth/callback",
        )
        self._data_dir = Path(os.path.expanduser(
            os.getenv("DB_PATH", "~/.mmo_agent/agent.db"))).parent
        self._token_path = self._data_dir / "google_token.json"

    # ── availability ───────────────────────────────────────────

    def is_available(self) -> bool:
        """True when OAuth credentials are configured (doesn't require a token yet)."""
        return bool(self.client_id and self.client_secret)

    def is_connected(self) -> bool:
        """True when a token file exists — the user completed the OAuth flow."""
        return self._token_path.exists()

    def test(self) -> bool:
        if not self.is_connected():
            return False
        token = self._get_valid_access_token()
        if not token:
            return False
        try:
            import requests
            r = requests.get(self.USERINFO_URL,
                             headers={"Authorization": f"Bearer {token}"}, timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    # ── OAuth2 flow ────────────────────────────────────────────

    def get_auth_url(self, state: str = "tobi") -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict:
        """Exchange the authorization code for access + refresh tokens."""
        import requests
        r = requests.post(self.TOKEN_URL, data={
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=15)
        if r.status_code != 200:
            logger.warning(f"Google OAuth exchange failed HTTP {r.status_code}: {r.text[:200]}")
            return {"error": r.text[:500]}
        data = r.json()
        self._save_token(data)
        return data

    def revoke(self) -> bool:
        """Disconnect — revoke tokens and delete the local token file."""
        token = self._load_token()
        access = token.get("access_token", "")
        if access:
            try:
                import requests
                requests.post(f"{self.REVOKE_URL}?token={access}", timeout=10)
            except Exception:
                pass
        try:
            self._token_path.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    # ── token persistence ──────────────────────────────────────

    def _save_token(self, raw: dict):
        self._data_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "access_token": raw.get("access_token", ""),
            "refresh_token": raw.get("refresh_token", ""),
            "scope": raw.get("scope", " ".join(self.SCOPES)),
            "token_type": raw.get("token_type", "Bearer"),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "expires_in": raw.get("expires_in", 3600),
        }
        with open(self._token_path, "w") as f:
            json.dump(record, f, indent=2)

    def _load_token(self) -> dict:
        if not self._token_path.exists():
            return {}
        try:
            with open(self._token_path) as f:
                return json.load(f)
        except Exception:
            return {}

    def _refresh_access_token(self) -> str:
        token = self._load_token()
        refresh = token.get("refresh_token", "")
        if not refresh:
            return ""
        try:
            import requests
            r = requests.post(self.TOKEN_URL, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            }, timeout=15)
            if r.status_code != 200:
                logger.warning(f"Google token refresh failed HTTP {r.status_code}")
                return ""
            data = r.json()
            token["access_token"] = data.get("access_token", "")
            token["saved_at"] = datetime.now(timezone.utc).isoformat()
            token["expires_in"] = data.get("expires_in", 3600)
            if data.get("refresh_token"):
                token["refresh_token"] = data["refresh_token"]
            self._data_dir.mkdir(parents=True, exist_ok=True)
            with open(self._token_path, "w") as f:
                json.dump(token, f, indent=2)
            return token["access_token"]
        except Exception as e:
            logger.warning(f"Google token refresh error: {e}")
            return ""

    def _get_valid_access_token(self) -> str:
        """Return a non-expired access token, refreshing automatically."""
        token = self._load_token()
        access = token.get("access_token", "")
        if not access:
            return ""
        saved_at = token.get("saved_at", "")
        if saved_at:
            try:
                age = (datetime.now(timezone.utc) -
                       datetime.fromisoformat(saved_at)).total_seconds()
                if age > 3300:
                    return self._refresh_access_token()
            except Exception:
                pass
        return access

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_valid_access_token()}",
                "Accept": "application/json"}

    # ── Google Drive ───────────────────────────────────────────

    def list_drive_files(self, query: str = "", limit: int = 20) -> list:
        """List Drive files. query = Google Drive Q-syntax (e.g. "name contains 'report'")."""
        if not self.is_connected():
            return []
        try:
            import requests
            params: dict = {
                "pageSize": min(limit, 100),
                "fields": "files(id,name,mimeType,size,modifiedTime,webViewLink,iconLink)",
                "orderBy": "modifiedTime desc",
            }
            if query:
                params["q"] = query
            r = requests.get("https://www.googleapis.com/drive/v3/files",
                             headers=self._headers(), params=params, timeout=15)
            if r.status_code != 200:
                logger.warning(f"Drive list HTTP {r.status_code}: {r.text[:200]}")
                return []
            return r.json().get("files", [])
        except Exception as e:
            logger.warning(f"Google Drive list error: {e}")
            return []

    def get_drive_file(self, file_id: str) -> dict:
        """Get file metadata."""
        if not self.is_connected():
            return {}
        try:
            import requests
            r = requests.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=self._headers(),
                params={"fields": "id,name,mimeType,size,modifiedTime,createdTime,description,webViewLink,parents"},
                timeout=10)
            return r.json() if r.status_code == 200 else {}
        except Exception as e:
            logger.warning(f"Google Drive get error: {e}")
            return {}

    def download_drive_file(self, file_id: str, mime_type: str = "") -> str:
        """Download a file's content as text. For Google Docs/Sheets/Slides, specify
        a target mime (e.g. 'text/plain', 'text/csv', 'application/pdf')."""
        if not self.is_connected():
            return ""
        try:
            import requests
            params = {"alt": "media"}
            if mime_type:
                params["mimeType"] = mime_type
            r = requests.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=self._headers(), params=params, timeout=30)
            if r.status_code != 200:
                return ""
            return r.text[:16000]
        except Exception as e:
            logger.warning(f"Google Drive download error: {e}")
            return ""

    def export_drive_doc(self, file_id: str, mime_type: str = "text/plain") -> str:
        """Export a Google Docs/Sheets/Slides file to the given format."""
        if not self.is_connected():
            return ""
        try:
            import requests
            r = requests.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                headers=self._headers(), params={"mimeType": mime_type}, timeout=30)
            if r.status_code != 200:
                return ""
            return r.text[:16000]
        except Exception as e:
            logger.warning(f"Google Drive export error: {e}")
            return ""

    # ── Gmail ──────────────────────────────────────────────────

    def list_gmail_messages(self, query: str = "", limit: int = 10) -> list:
        """List message IDs matching a query. query = Gmail search syntax."""
        if not self.is_connected():
            return []
        try:
            import requests
            params: dict = {"maxResults": min(limit, 100)}
            if query:
                params["q"] = query
            r = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/messages",
                             headers=self._headers(), params=params, timeout=15)
            if r.status_code != 200:
                logger.warning(f"Gmail list HTTP {r.status_code}: {r.text[:200]}")
                return []
            return r.json().get("messages", [])
        except Exception as e:
            logger.warning(f"Gmail list error: {e}")
            return []

    def get_gmail_message(self, msg_id: str) -> dict:
        """Read a single message — returns headers (From/Subject/Date) + body text."""
        if not self.is_connected():
            return {}
        try:
            import requests
            r = requests.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}",
                headers=self._headers(),
                params={"format": "full"}, timeout=15)
            if r.status_code != 200:
                return {}
            data = r.json()
            payload = data.get("payload", {})
            headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
            body = self._extract_gmail_body(payload)
            return {
                "id": msg_id,
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": data.get("snippet", ""),
                "body": body[:8000],
            }
        except Exception as e:
            logger.warning(f"Gmail get error: {e}")
            return {}

    @staticmethod
    def _extract_gmail_body(payload: dict) -> str:
        import base64
        def _decode(data: str) -> str:
            try:
                return base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
            except Exception:
                return ""
        if payload.get("body", {}).get("data"):
            return _decode(payload["body"]["data"])
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return _decode(part["body"]["data"])
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
                return _decode(part["body"]["data"])
        return ""

    # ── Google Calendar ────────────────────────────────────────

    def list_calendar_events(self, max_results: int = 10) -> list:
        """List upcoming calendar events."""
        if not self.is_connected():
            return []
        try:
            import requests
            time_min = datetime.now(timezone.utc).isoformat()
            r = requests.get(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers=self._headers(),
                params={"maxResults": min(max_results, 50), "orderBy": "startTime",
                        "singleEvents": True, "timeMin": time_min},
                timeout=15)
            if r.status_code != 200:
                logger.warning(f"Calendar list HTTP {r.status_code}: {r.text[:200]}")
                return []
            return r.json().get("items", [])
        except Exception as e:
            logger.warning(f"Calendar list error: {e}")
            return []


class VercelIntegration:
    def __init__(self):
        self.token = os.getenv("VERCEL_TOKEN", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def is_available(self) -> bool:
        return bool(self.token)

    def test(self) -> bool:
        if not self.is_available():
            return False
        try:
            import requests
            r = requests.get("https://api.vercel.com/v2/user", headers=self.headers, timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    def list_deployments(self, limit: int = 3) -> list:
        if not self.is_available():
            return []
        try:
            import requests
            r = requests.get(
                "https://api.vercel.com/v6/deployments",
                headers=self.headers,
                params={"limit": limit},
                timeout=10,
            )
            return r.json().get("deployments", []) if r.status_code == 200 else []
        except Exception as e:
            logger.warning(f"Vercel list_deployments error: {e}")
            return []

    def get_latest_deployment(self, project: str) -> dict:
        if not self.is_available():
            return {}
        deployments = self.list_deployments(limit=1)
        return deployments[0] if deployments else {}


class SupabaseIntegration:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL", "")
        self.anon_key = os.getenv("SUPABASE_ANON_KEY", "")
        self.headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.anon_key}",
            "Content-Type": "application/json",
        }

    def is_available(self) -> bool:
        return bool(self.url and self.anon_key)

    def test(self) -> bool:
        if not self.is_available():
            return False
        try:
            import requests
            r = requests.get(f"{self.url}/rest/v1/", headers=self.headers, timeout=10)
            return r.status_code in (200, 404)
        except Exception:
            return False

    def query_table(self, table: str, limit: int = 10) -> list:
        if not self.is_available():
            return []
        try:
            import requests
            r = requests.get(
                f"{self.url}/rest/v1/{table}",
                headers={**self.headers, "Range": f"0-{limit - 1}"},
                timeout=10,
            )
            return r.json() if r.status_code == 200 else []
        except Exception as e:
            logger.warning(f"Supabase query error: {e}")
            return []

    def insert_row(self, table: str, data: dict) -> dict:
        if not self.is_available():
            return {}
        try:
            import requests
            r = requests.post(
                f"{self.url}/rest/v1/{table}",
                headers={**self.headers, "Prefer": "return=representation"},
                json=data,
                timeout=10,
            )
            result = r.json()
            return result[0] if isinstance(result, list) and result else result
        except Exception as e:
            logger.warning(f"Supabase insert error: {e}")
            return {}


# ─────────────────────────────────────────
# Registry
# ─────────────────────────────────────────

_integrations = {
    "notion":   NotionIntegration,
    "github":   GitHubIntegration,
    "google":   GoogleIntegration,
    "vercel":   VercelIntegration,
    "supabase": SupabaseIntegration,
}

# The environment names each connector reads, kept beside the classes that read them so the
# two cannot drift. Vault secrets are stored under these same names, which is what lets a
# caller tell "no key was ever saved" apart from "the key is saved but the vault is locked" —
# two states that both make is_available() False and used to be reported identically.
REQUIRED_SECRETS: dict[str, tuple[str, ...]] = {
    "notion":   ("NOTION_API_KEY",),
    "github":   ("GITHUB_TOKEN",),
    "google":   ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
    "vercel":   ("VERCEL_TOKEN",),
    "supabase": ("SUPABASE_URL", "SUPABASE_ANON_KEY"),
}


def check_all() -> dict:
    """Returns {name: is_available} for all integrations."""
    return {name: cls().is_available() for name, cls in _integrations.items()}


def get_integration(name: str):
    cls = _integrations.get(name.lower())
    return cls() if cls else None
