"""HTTP: polite downloads (identification with a contact URL, Retry-After honoured) and the GitHub REST API."""
from __future__ import annotations

import http.client
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable

USER_AGENT = 'worldwide-tv-logos/0.1 (+https://github.com/worldwide-tv-logos/database)'
MAX_DOWNLOAD = 5_000_000
TIMEOUT = 60


class DownloadError(RuntimeError):
    pass


def data_uri(url: str, max_size: int = MAX_DOWNLOAD) -> bytes:
    """Image inlined in a page and copied as a data: URI (an SVG logo drawn in the page of the channel's website):
    `data:image/svg+xml,<percent-encoded>` or `data:image/<type>;base64,<data>`."""
    import base64
    import urllib.parse
    head, _, payload = url.partition(',')
    try:
        data = base64.b64decode(payload, validate=False) if head.endswith(';base64') else \
            urllib.parse.unquote_to_bytes(payload)
    except ValueError:
        raise DownloadError('unreadable data: image') from None
    if not data or len(data) > max_size:
        raise DownloadError('empty or too large data: image')
    return data


WIKI_FILE_RE = re.compile(r'^https://([a-z0-9.-]+\.(?:wikipedia|wikimedia)\.org)/wiki/[^#]*?(?:#/media/)?'
                          r'(?:File|Fichier|Datei|Archivo|Ficheiro|Arquivo|Bestand|Plik|Immagine|Fil|Tiedosto|Soubor|'
                          r'Fitxer|Dosya|Файл|ملف):([^/#?]+)$', re.IGNORECASE)


def image_url(url: str) -> str:
    """The image itself for the page of a Wikipedia or Wikimedia Commons file (`.../wiki/File:X.svg`, or an article
    opened on it: `.../wiki/Article#/media/Fichier:X.png`): what people copy from the address bar."""
    m = WIKI_FILE_RE.match(url.strip())
    return f'https://{m.group(1)}/wiki/Special:FilePath/{m.group(2)}' if m else url


def download(url: str, *, opener: Callable = urllib.request.urlopen, sleep: Callable = time.sleep,
             attempts: int = 3, accept: str = 'image/*,*/*;q=0.5', max_size: int = MAX_DOWNLOAD,
             user_agent: str = USER_AGENT) -> bytes:
    if url.startswith('data:image/'):
        return data_uri(url, max_size)
    if not url.startswith('https://'):
        raise DownloadError('only https:// links (or an image copied as data:image/...) are accepted')
    import urllib.parse
    url = image_url(url)
    url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")      # spaces in a website's image path
    for _ in range(attempts):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': user_agent, 'Accept': accept})
            with opener(req, timeout=TIMEOUT) as resp:
                data = resp.read(max_size + 1)
            if len(data) > max_size:
                raise DownloadError(f'file larger than {max_size // 1_000_000} MB')
            return data
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503):
                raise DownloadError(f'HTTP {exc.code}') from None
            sleep(min(int(exc.headers.get('Retry-After') or 120), 600) + 1)
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as exc:
            # ValueError: malformed URL; HTTPException: response cut by the site (IncompleteRead, bad chunk)
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

    def open_issues(self, label: str) -> list[dict]:
        return [i for i in self.call('GET', f'/issues?state=open&labels={label}&per_page=100')
                if 'pull_request' not in i]

    def create_issue(self, title: str, body: str, labels: list[str]) -> int:
        return self.call('POST', '/issues', {'title': title, 'body': body, 'labels': labels})['number']

    def edit_issue(self, number: int, **fields) -> None:
        self.call('PATCH', f'/issues/{number}', fields)
