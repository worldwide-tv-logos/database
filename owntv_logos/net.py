"""HTTP: polite downloads (identification with a contact URL, Retry-After honoured) and the GitHub REST API."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable

USER_AGENT = 'tv-logos-owntv/0.1 (+https://github.com/alexandre-meline/tv-logos-owntv)'
MAX_DOWNLOAD = 5_000_000
TIMEOUT = 60


class DownloadError(RuntimeError):
    pass


def download(url: str, *, opener: Callable = urllib.request.urlopen, sleep: Callable = time.sleep,
             attempts: int = 3) -> bytes:
    if not url.startswith('https://'):
        raise DownloadError('only https:// links are accepted')
    for _ in range(attempts):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'image/*,*/*;q=0.5'})
            with opener(req, timeout=TIMEOUT) as resp:
                data = resp.read(MAX_DOWNLOAD + 1)
            if len(data) > MAX_DOWNLOAD:
                raise DownloadError(f'file larger than {MAX_DOWNLOAD // 1_000_000} MB')
            return data
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503):
                raise DownloadError(f'HTTP {exc.code}') from None
            sleep(min(int(exc.headers.get('Retry-After') or 120), 600) + 1)
        except (urllib.error.URLError, OSError) as exc:
            raise DownloadError(f'network error ({getattr(exc, "reason", exc)})') from None
    raise DownloadError(f'still refused after {attempts} attempts (site busy)')


class GitHub:
    """Minimal REST client for issues of the current repository (GITHUB_REPOSITORY, GITHUB_TOKEN)."""

    def __init__(self, repo: str | None = None, token: str | None = None, opener: Callable = urllib.request.urlopen):
        self.repo = repo or os.environ['GITHUB_REPOSITORY']
        self.token = token or os.environ.get('GITHUB_TOKEN', '')
        self.opener = opener

    def call(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(f'https://api.github.com/repos/{self.repo}{path}', method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Accept': 'application/vnd.github+json', 'User-Agent': USER_AGENT,
                                              **({'Authorization': f'Bearer {self.token}'} if self.token else {})})
        with self.opener(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else None

    def approved_issues(self) -> list[dict]:
        out, page = [], 1
        while True:
            batch = self.call('GET', f'/issues?state=open&labels=approved&per_page=100&page={page}')
            out += [i for i in batch if 'pull_request' not in i]
            if len(batch) < 100:
                return sorted(out, key=lambda i: i['number'])
            page += 1

    def comment(self, number: int, text: str) -> None:
        self.call('POST', f'/issues/{number}/comments', {'body': text})

    def add_labels(self, number: int, labels: list[str]) -> None:
        self.call('POST', f'/issues/{number}/labels', {'labels': labels})

    def remove_label(self, number: int, label: str) -> None:
        try:
            self.call('DELETE', f'/issues/{number}/labels/{label}')
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
