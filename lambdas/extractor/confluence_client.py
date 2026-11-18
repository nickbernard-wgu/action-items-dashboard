"""
Minimal Confluence HTTP client for the action-items extractor Lambda.

Accepts credentials as constructor parameters; does NOT import config_loader.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class ConfluenceClient:
    def __init__(
        self,
        site: str,
        email: str,
        api_token: str,
        max_workers: int = 6,
        timeout: int = 30,
    ):
        self._base_url = f"https://{site}"
        self._timeout = timeout
        self._user_cache: dict = {}

        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session = requests.Session()
        self._session.mount("https://", adapter)
        self._session.auth = requests.auth.HTTPBasicAuth(email, api_token)

    def fetch_children_with_versions(self, parent_id: str) -> list:
        """Return child pages under parent_id with their current versions.

        Returns:
            List of {"id": str, "title": str, "version": int}
        """
        results = []
        url = f"{self._base_url}/wiki/api/v2/pages/{parent_id}/children"
        params: dict = {"limit": 250}

        while url:
            resp = self._session.get(url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            for page in data.get("results", []):
                results.append({
                    "id": str(page["id"]),
                    "title": page.get("title", ""),
                    "version": page.get("version", {}).get("number", 0),
                })

            # Pagination via cursor
            next_cursor = data.get("_links", {}).get("next")
            if next_cursor:
                # next_cursor is a relative path like /wiki/api/v2/pages/.../children?cursor=...
                url = f"{self._base_url}{next_cursor}"
                params = {}  # cursor already embedded in URL
            else:
                url = None

        return results

    def get_page_body(self, page_id: str) -> tuple:
        """Fetch the storage-format body of a page.

        Returns:
            (storage_body: str, title: str, version: int)
        """
        url = f"{self._base_url}/wiki/api/v2/pages/{page_id}"
        resp = self._session.get(
            url,
            params={"body-format": "storage"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        body = data.get("body", {}).get("storage", {}).get("value", "")
        title = data.get("title", "")
        version = data.get("version", {}).get("number", 0)
        return body, title, version

    def get_user_display_name(self, account_id: str) -> str:
        """Resolve a Confluence account ID to a display name.

        Results are cached per client instance. Returns "" on error.
        """
        if account_id in self._user_cache:
            return self._user_cache[account_id]

        try:
            url = f"{self._base_url}/wiki/rest/api/user"
            resp = self._session.get(
                url,
                params={"accountId": account_id},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            name = resp.json().get("displayName", "")
        except Exception:
            name = ""

        self._user_cache[account_id] = name
        return name
