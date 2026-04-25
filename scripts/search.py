#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


SWITCHBREW_URL = "https://switchbrew.org/w/index.php?title=Title_list/Games&mobileaction=toggle_view_desktop"
SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR.parent / "data"
CACHE_FILE = DATA_DIR / ".switchbrew_title_cache.json"
GAMES_JSON = DATA_DIR / "games.json"
CACHE_MAX_AGE_DAYS = 7


@dataclass
class GameEntry:
    title_id: str
    name: str
    region: str
    version_count: int


def parse_switchbrew_table(html: str) -> list[GameEntry]:
    entries: list[GameEntry] = []

    table_match = re.search(
        r"<table[^>]*>(.*?)</table>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not table_match:
        return entries

    for row in re.findall(r"<tr>(.*?)</tr>", table_match.group(1), flags=re.IGNORECASE | re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.IGNORECASE | re.DOTALL)
        if len(cells) < 2:
            continue

        title_id_match = re.search(r"([0-9A-Fa-f]{16})", cells[0])
        if not title_id_match:
            continue

        title_id = title_id_match.group(1).upper()
        name = re.sub(r"<[^>]+>", "", cells[1]).strip()
        if not name:
            continue

        region = ""
        version_count = 0
        for cell in cells[2:]:
            cleaned = re.sub(r"<[^>]+>", "", cell).strip()
            if cleaned in ("CHN", "EUR", "JPN", "KOR", "USA"):
                region = cleaned
            elif re.match(r"^[0-9]+( [0x[0-9a-f]+)*$", cleaned.replace(" ", "")):
                parts = cleaned.split()
                version_count = len(parts)

        entries.append(GameEntry(
            title_id=title_id,
            name=name,
            region=region,
            version_count=version_count,
        ))

    return entries


def load_cache() -> list[GameEntry] | None:
    if not CACHE_FILE.exists():
        return None
    try:
        mtime = CACHE_FILE.stat().st_mtime
        import time
        if (time.time() - mtime) > (CACHE_MAX_AGE_DAYS * 86400):
            return None
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return [GameEntry(**item) for item in data]
    except Exception:
        return None


def save_cache(entries: list[GameEntry]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = [vars(GameEntry(e.title_id, e.name, e.region, e.version_count)) for e in entries]
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_entries() -> list[GameEntry]:
    existing = load_cache()
    if existing is not None:
        return existing

    print(f"Fetching title list from switchbrew.org (this may take a moment) ...", file=sys.stderr)
    try:
        request = urllib.request.Request(
            SWITCHBREW_URL,
            headers={"User-Agent": "switch-emu-cheat-codes/0.1 (+https://github.com)"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html = response.read().decode(charset, errors="replace")
    except urllib.error.URLError as exc:
        print(f"error: failed to fetch {SWITCHBREW_URL}: {exc}", file=sys.stderr)
        sys.exit(1)

    entries = parse_switchbrew_table(html)
    if entries:
        save_cache(entries)
        print(f"Cached {len(entries)} titles.", file=sys.stderr)
    return entries


def normalize_for_match(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def fuzzy_score(query: str, name: str) -> int:
    query_norm = normalize_for_match(query)
    name_norm = normalize_for_match(name)

    if query_norm == name_norm:
        return 1000
    if name_norm.startswith(query_norm):
        return 800 + (len(name_norm) - len(query_norm))
    if query_norm in name_norm:
        return 600 + (len(name_norm) - len(query_norm))

    query_chars = list(query_norm)
    score = 0
    for ch in name_norm:
        if query_chars and ch == query_chars[0]:
            score += 1
            query_chars.pop(0)
    if query_chars:
        return 0
    return max(0, score - abs(len(name_norm) - len(query_norm)))


def search_entries(entries: list[GameEntry], query: str, limit: int = 10) -> list[GameEntry]:
    scored = []
    for entry in entries:
        score = fuzzy_score(query, entry.name)
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: (-x[0], x[1].name))
    return [entry for _, entry in scored[:limit]]


def prompt_choice(entries: list[GameEntry], skip_confirm: bool = False) -> GameEntry | None:
    if not entries:
        return None
    if len(entries) == 1 and skip_confirm:
        return entries[0]
    if len(entries) == 1:
        print(f"Found: {entries[0].name} [{entries[0].title_id}]")
        resp = input("Is this the correct game? [Y/n] ").strip().lower()
        if resp in ("", "y", "yes"):
            return entries[0]
        return None

    print("\nMultiple matches found:\n")
    for i, entry in enumerate(entries, 1):
        versions_note = f" ({entry.version_count} versions)" if entry.version_count > 1 else ""
        print(f"  [{i}] {entry.name}{versions_note} [{entry.title_id}]")
    print("  [q] quit")

    while True:
        resp = input("\nSelect a number: ").strip().lower()
        if resp == "q":
            return None
        try:
            idx = int(resp) - 1
            if 0 <= idx < len(entries):
                return entries[idx]
        except ValueError:
            pass
        print("Please enter a number from the list, or 'q' to quit.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search Switch titles by name and optionally generate cheats.",
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Game name to search for (case-insensitive, partial match).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Force-refresh the title cache instead of using cached data.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of search results to show. Default: %(default)s",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation when exactly one match is found.",
    )
    parser.add_argument(
        "-g", "--generate",
        action="store_true",
        help="After selection, immediately run generator.py with the chosen title ID.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="cheats",
        help="Output directory for generated cheats (used with --generate). Default: %(default)s",
    )
    return parser


def main() -> int:
    import subprocess
    import os

    parser = build_parser()
    args = parser.parse_args()

    if args.no_cache and CACHE_FILE.exists():
        CACHE_FILE.unlink()

    entries = fetch_entries()

    if not args.query:
        print(f"Loaded {len(entries)} titles from cache (or network).")
        print("Usage: python3 search.py <game name>")
        print(f"Cache file: {CACHE_FILE}")
        return 0

    results = search_entries(entries, args.query, args.limit)

    if not results:
        print(f"No matches found for: {args.query}", file=sys.stderr)
        return 1

    chosen = prompt_choice(results, args.yes)
    if not chosen:
        print("No game selected.", file=sys.stderr)
        return 1

    print(f"\nSelected: {chosen.name}")
    print(f"Title ID: {chosen.title_id}")

    if args.generate:
        print(f"\nGenerating cheats to {args.output_dir} ...", file=sys.stderr)
        script_dir = Path(__file__).parent.resolve()
        result = subprocess.run(
            [sys.executable, "generator.py", chosen.title_id, "-o", args.output_dir],
            cwd=script_dir,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        return result.returncode

    print(f"\nTo generate cheats, run:")
    print(f"  python3 generator.py {chosen.title_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())