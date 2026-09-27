"""Read-only data access of the dashboard (G4 ANNEX_2 D-4, ANNEX_3 I-5): HTTPS GET on the GitHub contents API of the two repositories
only, with the USER's fine-grained read-only token from Streamlit Secrets. Nothing is written, logged or cached on disk; a failure raises
a short error without the response body or any value (X-1). The only module of track_c/ops that uses the network."""
from __future__ import annotations

import base64
import json
import urllib.request

API = "https://api.github.com"
STATE_REPO, INPUTS_REPO = "yuuu-yeee/AutoTrader", "yuuu-yeee/AutoTrader-ops-inputs"
STATE_BRANCH = "ops/phase7-shadow-state"
MODES = ("synthetic", "live")


class ReaderError(RuntimeError):
    pass


class GitHubReader:
    def __init__(self, token: str, mode: str = "synthetic"):
        if mode not in MODES or not isinstance(token, str) or not token:
            raise ReaderError("READER_CONFIGURATION")
        self._token, self.mode = token, mode

    def _get(self, repo: str, path: str, ref: str | None = None) -> dict | list:
        if repo not in (STATE_REPO, INPUTS_REPO):
            raise ReaderError("REPOSITORY_NOT_ALLOWED")
        url = f"{API}/repos/{repo}/{path}" + (f"?ref={ref}" if ref else "")
        request = urllib.request.Request(url, method="GET", headers={"Authorization": f"Bearer {self._token}",
                                                                     "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            raise ReaderError("READ_FAILED") from None  # no URL, status body or value in the message

    def _file(self, repo: str, path: str, ref: str | None = None) -> dict:
        item = self._get(repo, f"contents/{path}", ref)
        return json.loads(base64.b64decode(item["content"]).decode("utf-8"))

    def state(self) -> dict:
        return self._file(STATE_REPO, f"{self.mode}/state.json", STATE_BRANCH)

    def record(self, digest: str) -> dict:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ReaderError("DIGEST_INVALID")
        return self._file(INPUTS_REPO, f"{self.mode}/{digest}.json")

    def last_run_time_utc(self) -> str | None:
        commits = self._get(STATE_REPO, f"commits?sha={STATE_BRANCH}&path={self.mode}/state.json&per_page=1")
        return commits[0]["commit"]["committer"]["date"] if commits else None
