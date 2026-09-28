"""Read-only data access of the dashboard (G4 ANNEX_2 D-4, ANNEX_3 I-5): HTTPS GET on the GitHub contents API of the two repositories
only, with the USER's fine-grained read-only token from Streamlit Secrets. Nothing is written, logged or cached on disk; a failure raises
a short error without the response body or any value (X-1). The only module of track_c/ops that uses the network."""
from __future__ import annotations

import base64
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.github.com"
STATE_REPO, INPUTS_REPO = "yuuu-yeee/AutoTrader", "yuuu-yeee/AutoTrader-ops-inputs"
STATE_BRANCH = "ops/phase7-shadow-state"
EXPERIMENT_BRANCH = "ops/experiment-state"  # EXPERIMENT_ACCOUNT_CONTRACT_V2
SLOT_ID, DAY = re.compile(r"[A-Z0-9][A-Z0-9-]{0,40}"), re.compile(r"\d{4}-\d{2}-\d{2}")
MODES = ("synthetic", "live")
FOLDERS = {"synthetic": "synthetic_v2", "live": "live"}  # G4 ANNEX_6 A6-3: the synthetic state restarted in synthetic_v2/


class ReaderError(RuntimeError):
    pass


class GitHubReader:
    def __init__(self, token: str, mode: str = "synthetic"):
        if mode not in MODES or not isinstance(token, str) or not token:
            raise ReaderError("READER_CONFIGURATION")
        self._token, self.mode, self.folder = token, mode, FOLDERS[mode]

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
        return self._file(STATE_REPO, f"{self.folder}/state.json", STATE_BRANCH)

    def record(self, digest: str) -> dict:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ReaderError("DIGEST_INVALID")
        return self._file(INPUTS_REPO, f"{self.folder}/{digest}.json")

    def last_run_time_utc(self) -> str | None:
        commits = self._get(STATE_REPO, f"commits?sha={STATE_BRANCH}&path={self.folder}/state.json&per_page=1")
        return commits[0]["commit"]["committer"]["date"] if commits else None

    def state_history(self) -> list[dict]:
        """G4 ANNEX_11: every committed state of the folder, oldest first (read in memory when the page opens; nothing is kept)."""
        shas, page = [], 1
        while True:
            batch = self._get(STATE_REPO, f"commits?sha={STATE_BRANCH}&path={self.folder}/state.json&per_page=100&page={page}")
            shas += [c["sha"] for c in batch]
            if len(batch) < 100:
                break
            page += 1
        for sha in shas:
            if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
                raise ReaderError("COMMIT_INVALID")
        with ThreadPoolExecutor(max_workers=8) as pool:
            states = list(pool.map(lambda sha: self._file(STATE_REPO, f"{self.folder}/state.json", sha), shas))
        return states[::-1]

    # EXPERIMENT_ACCOUNT_CONTRACT_V2: the experiment account's state (ops/experiment-state) and data (ops-inputs experiment/), read only
    def experiment_slots(self) -> list[str]:
        try:
            items = self._get(STATE_REPO, "contents/slots", EXPERIMENT_BRANCH)
        except ReaderError:
            return []  # no slot state yet
        return sorted(i["name"] for i in items if i.get("type") == "dir" and SLOT_ID.fullmatch(i.get("name", "")))

    def experiment_state(self, slot: str) -> dict:
        if not SLOT_ID.fullmatch(slot):
            raise ReaderError("SLOT_ID_INVALID")
        return self._file(STATE_REPO, f"slots/{slot}/state.json", EXPERIMENT_BRANCH)

    def experiment_closes(self, sessions: list[str]) -> dict[str, dict]:
        if any(not DAY.fullmatch(s) for s in sessions):
            raise ReaderError("SESSION_INVALID")
        with ThreadPoolExecutor(max_workers=8) as pool:
            docs = list(pool.map(lambda s: self._file(INPUTS_REPO, f"experiment/bars/{s}.json"), sessions))
        return {s: doc["bars"] for s, doc in zip(sessions, docs)}

    def experiment_fx(self) -> dict[str, str]:
        return self._file(INPUTS_REPO, "experiment/fx.json")

    def records(self, digests: dict[str, str]) -> dict[str, dict]:
        """G4 ANNEX_11: {session: input record} for the given {session: digest}."""
        sessions = sorted(digests)
        with ThreadPoolExecutor(max_workers=8) as pool:
            return dict(zip(sessions, pool.map(lambda s: self.record(digests[s]), sessions)))
