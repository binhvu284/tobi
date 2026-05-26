"""Integrations - Tobi Agent
External service connectors. Each has is_available() and test().
"""
from dotenv import load_dotenv
load_dotenv()

import os
import logging
from typing import Optional

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


class GitHubIntegration:
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN", "")
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def is_available(self) -> bool:
        return bool(self.token)

    def test(self) -> bool:
        if not self.is_available():
            return False
        try:
            import requests
            r = requests.get("https://api.github.com/user", headers=self.headers, timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    def get_repo_info(self, repo: str) -> dict:
        if not self.is_available():
            return {}
        try:
            import requests
            r = requests.get(f"https://api.github.com/repos/{repo}", headers=self.headers, timeout=10)
            return r.json() if r.status_code == 200 else {}
        except Exception as e:
            logger.warning(f"GitHub get_repo error: {e}")
            return {}

    def list_issues(self, repo: str, limit: int = 5) -> list:
        if not self.is_available():
            return []
        try:
            import requests
            r = requests.get(
                f"https://api.github.com/repos/{repo}/issues",
                headers=self.headers,
                params={"per_page": limit, "state": "open"},
                timeout=10,
            )
            return r.json() if r.status_code == 200 else []
        except Exception as e:
            logger.warning(f"GitHub list_issues error: {e}")
            return []

    def create_issue(self, repo: str, title: str, body: str) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            import requests
            r = requests.post(
                f"https://api.github.com/repos/{repo}/issues",
                headers=self.headers,
                json={"title": title, "body": body},
                timeout=10,
            )
            return r.json().get("html_url")
        except Exception as e:
            logger.warning(f"GitHub create_issue error: {e}")
            return None

    def get_recent_commits(self, repo: str, limit: int = 5) -> list:
        if not self.is_available():
            return []
        try:
            import requests
            r = requests.get(
                f"https://api.github.com/repos/{repo}/commits",
                headers=self.headers,
                params={"per_page": limit},
                timeout=10,
            )
            return r.json() if r.status_code == 200 else []
        except Exception as e:
            logger.warning(f"GitHub get_commits error: {e}")
            return []


class GoogleIntegration:
    """Placeholder — connect via Google OAuth in Phase 2."""

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def test(self) -> bool:
        # Phase 2: implement OAuth + Google Workspace API
        return False


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


def check_all() -> dict:
    """Returns {name: is_available} for all integrations."""
    return {name: cls().is_available() for name, cls in _integrations.items()}


def get_integration(name: str):
    cls = _integrations.get(name.lower())
    return cls() if cls else None
