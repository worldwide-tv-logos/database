"""Reading web pages like a browser does.

A plain request first (fast, with a browser's User-Agent); when the site refuses it (403, network error) or when
asked for the page as rendered (logos added by JavaScript), a headless Chromium (Playwright, optional: `uv sync
--extra browser` then `uv run playwright install chromium`). Measured on 18 channel websites from a GitHub runner on
2026-11-23: 14 read by the plain request, 13 by the browser, 15 by one or the other (the others: dead addresses).

The browser is started once and reused; one page at a time.
"""
from __future__ import annotations

import atexit
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/130.0 Safari/537.36')
TIMEOUT = 20
MAX_PAGE = 5_000_000
CONSENT_RE = re.compile(r"^\s*(accept( all)?|aceptar( todo| todas)?|acepto|accepter( tout)?|tout accepter|akzeptieren"
                        r"|alle akzeptieren|accetta( tutto)?|aceitar( tudo)?|acceptar( tot)?|i agree|agree|allow all|ok"
                        r"|d'accord|entendido|got it)\s*$", re.IGNORECASE)    # "accept" buttons of cookie banners


@dataclass
class Page:
    url: str                      # the address asked
    final: str = ''               # the address after redirections
    html: str = ''
    status: int = 0
    how: str = ''                 # plain | browser
    error: str = ''               # why it could not be read ('' when read)

    @property
    def ok(self) -> bool:
        return not self.error and 200 <= self.status < 400 and bool(self.html)


def plain(url: str, opener=urllib.request.urlopen, timeout: float = TIMEOUT) -> Page:
    page = Page(url, how='plain')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': BROWSER_UA, 'Accept': 'text/html,*/*;q=0.8',
                                                   'Accept-Language': 'en,fr;q=0.8,es;q=0.7,de;q=0.6,it;q=0.5'})
        with opener(req, timeout=timeout) as resp:
            page.status, page.final = resp.status, resp.geturl()
            page.html = resp.read(MAX_PAGE).decode('utf-8', errors='replace')
    except urllib.error.HTTPError as exc:
        page.status, page.error = exc.code, f'HTTP {exc.code}'
    except Exception as exc:  # noqa: BLE001 - every failure is reported, never raised
        page.error = f'{type(exc).__name__}'
    return page


class Browser:
    """A headless Chromium, started on first use (None when Playwright or Chromium is missing)."""
    _instance: Browser | None = None
    _failed = False

    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._page = self._browser.new_page(user_agent=BROWSER_UA, viewport={'width': 1280, 'height': 800})
        atexit.register(self.close)

    @classmethod
    def get(cls) -> Browser | None:
        if cls._instance is None and not cls._failed:
            try:
                cls._instance = cls()
            except Exception:  # noqa: BLE001 - no Playwright or no Chromium: plain requests only
                cls._failed = True
        return cls._instance

    def open(self, url: str, wait: float = 2.5) -> Page:
        page = Page(url, how='browser')
        try:
            resp = self._page.goto(url, wait_until='domcontentloaded', timeout=TIMEOUT * 1000)
            self._page.wait_for_timeout(int(wait * 1000))
            self._close_consent()
            page.status = resp.status if resp else 0
            page.final = self._page.url
            page.html = self._page.content()
            if page.status >= 400:
                page.error = f'HTTP {page.status}'
        except Exception as exc:  # noqa: BLE001
            page.error = type(exc).__name__
        return page

    def _close_consent(self) -> None:
        """Close a cookie banner (it would hide the page on the capture): its "accept" button, in a few languages."""
        try:
            button = self._page.get_by_role('button', name=CONSENT_RE).first
            if button.is_visible(timeout=500):
                button.click(timeout=2000)
                self._page.wait_for_timeout(800)
        except Exception:  # noqa: BLE001, S110 - no banner, or one that cannot be closed
            pass

    def screenshot(self, height: int = 420) -> bytes:
        """The top of the page last opened (header and logo), as PNG."""
        return self._page.screenshot(clip={'x': 0, 'y': 0, 'width': 1280, 'height': height})

    def close(self) -> None:
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:  # noqa: BLE001, S110 - already closed
            pass
        Browser._instance = None


def fetch(url: str, rendered: bool = False, browser: bool = True, opener=urllib.request.urlopen) -> Page:
    """A page read by a plain request, else (or, with `rendered`, also) by the browser when it is available."""
    page = plain(url, opener)
    if (rendered or not page.ok) and browser:
        b = Browser.get()
        if b is not None:
            other = b.open(url)
            if other.ok or not page.ok:
                return other
    return page


def screenshot(url: str) -> bytes | None:
    """The top of a page as shown by the browser, None when it cannot be shown."""
    b = Browser.get()
    if b is None:
        return None
    page = b.open(url)
    if not page.ok:
        return None
    try:
        return b.screenshot()
    except Exception:  # noqa: BLE001
        return None


def polite_pause(last: dict, host: str, pause: float) -> None:
    wait = last.get(host, 0.0) + pause - time.time()
    if wait > 0:
        time.sleep(wait)
    last[host] = time.time()
