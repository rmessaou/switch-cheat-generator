#!/usr/bin/env python3

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TINFOIL_API_URL = "https://tinfoil.media/Title/ApiJson/"
TINFOIL_TITLE_URL = "https://tinfoil.io/Title/"
SCRIPT_DIR = Path(__file__).parent.resolve()
LAST_REQUEST_TIME = 0.0
MIN_REQUEST_INTERVAL = 1.0


def _rate_limit() -> None:
    global LAST_REQUEST_TIME
    elapsed = time.time() - LAST_REQUEST_TIME
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    LAST_REQUEST_TIME = time.time()


def _make_request(url: str) -> dict | None:
    _rate_limit()
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://tinfoil.io/Title/",
                "Origin": "https://tinfoil.io",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset, errors="replace"))
    except Exception:
        return None


class TinfoilEntry:
    __slots__ = ("title_id", "name")
    def __init__(self, title_id: str, name: str):
        self.title_id = title_id
        self.name = name
    def __repr__(self):
        return f"TinfoilEntry({self.title_id}, {self.name!r})"


def parse_tinfoil_response(json_data: dict) -> list[TinfoilEntry]:
    entries: list[TinfoilEntry] = []
    data = json_data.get("data", [])
    if not isinstance(data, list):
        return entries
    
    for item in data:
        name_html = item.get("name", "")
        title_id = item.get("id", "")
        
        name_match = re.search(r">([^<]+)<", name_html)
        if name_match:
            name = name_match.group(1)
        else:
            name = name_html
        
        name = html.unescape(name)
        
        if title_id and len(title_id) == 16:
            entries.append(TinfoilEntry(title_id=title_id.upper(), name=name))
    
    return entries


def fetch_tinfoil_search(query: str, limit: int = 10) -> list[TinfoilEntry]:
    """
    Search tinfoil.io by fetching ALL titles and filtering locally.
    Note: The API doesn't support search param - browser filters client-side.
    """
    if not query or not query.strip():
        return []
    
    query_norm = query.strip().lower()
    entries = fetch_all_tinfoil_titles()
    
    def score(name: str) -> int:
        name_lower = name.lower()
        if query_norm == name_lower:
            return 1000
        if name_lower.startswith(query_norm):
            return 800 + (len(name_lower) - len(query_norm))
        if query_norm in name_lower:
            return 600 + (len(name_lower) - len(query_norm))
        return 0
    
    scored = [(score(e.name), e) for e in entries if score(e.name) > 0]
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:limit]]


def search_tinfoil(query: str, limit: int = 10) -> list[TinfoilEntry]:
    """
    Search tinfoil.io for titles matching query.
    Returns list of TinfoilEntry with title_id and name.
    """
    return fetch_tinfoil_search(query, limit)


def find_title_by_id(title_id: str) -> str | None:
    """
    Fetch game name by title ID from tinfoil.io.
    Returns game name or None if not found.
    """
    url = f"{TINFOIL_TITLE_URL}{title_id}"
    
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")
            match = re.search(r"<h1[^>]*>([^<]+)<", html)
            if match:
                return match.group(1)
    except Exception:
        pass
    
    return None


def find_title_id_online(game_name: str) -> tuple[str | None, str | None]:
    """
    Find title ID for a game name by searching tinfoil.io.
    First tries the API search, then tries fetching title pages directly.
    
    Returns (title_id, game_name) or (None, None) if not found.
    """
    if not game_name:
        return None, None
    
    entries = search_tinfoil(game_name, limit=5)
    if entries:
        return entries[0].title_id, entries[0].name
    
    return None, None


def fetch_all_tinfoil_titles() -> list[TinfoilEntry]:
    """
    Fetch ALL titles from tinfoil.io. The API returns all titles at once,
    filter is done client-side in browser. We fetch all and filter locally.
    """
    params = {
        "rating_content": "",
        "language": "",
        "category": "",
        "region": "us",
        "rating": "0",
        "_": str(int(time.time() * 1000)),
    }
    url = f"{TINFOIL_API_URL}?{urllib.parse.urlencode(params)}"
    
    json_data = _make_request(url)
    if json_data is None:
        return []
    
    return parse_tinfoil_response(json_data)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    if not query:
        print("Usage: python -m scripts.tinfoil_search <game name>")
        sys.exit(1)
    
    entries = search_tinfoil(query, limit=10)
    if not entries:
        print(f"No results found for: {query}")
        sys.exit(1)
    
    print(f"Results for '{query}':\n")
    for i, e in enumerate(entries, 1):
        print(f"  [{i}] {e.name} [{e.title_id}]")