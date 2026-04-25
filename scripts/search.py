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

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR.parent / "data"
GAMES_JSON = DATA_DIR / "games.json"

SWITCHBREW_URL = "https://switchbrew.org/w/index.php?title=Title_list/Games&mobileaction=toggle_view_desktop"
CACHE_FILE = DATA_DIR / ".switchbrew_title_cache.json"
CACHE_MAX_AGE_DAYS = 7

tinfoil_search = None


def _import_tinfoil():
    global tinfoil_search
    if tinfoil_search is not None:
        return
    
    tinfoil_path = SCRIPT_DIR / "tinfoil_search.py"
    if not tinfoil_path.exists():
        tinfoil_path = SCRIPT_DIR.parent / "scripts" / "tinfoil_search.py"
    
    if not tinfoil_path.exists():
        print(f"Warning: tinfoil_search.py not found", file=sys.stderr)
        return
    
    import importlib.util
    spec = importlib.util.spec_from_file_location("tinfoil_search", tinfoil_path)
    if spec is None:
        print(f"Warning: spec is None for {tinfoil_path}", file=sys.stderr)
        return
    if spec.loader is None:
        print(f"Warning: spec.loader is None for {tinfoil_path}", file=sys.stderr)
        return
    
    tinfoil_search = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tinfoil_search)
    print(f"Loaded tinfoil_search from {tinfoil_path}", file=sys.stderr)


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


def load_offline_games() -> list[dict]:
    if not GAMES_JSON.exists():
        return []
    try:
        return json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []


def search_offline_games(query: str, limit: int = 10) -> list[dict]:
    games = load_offline_games()
    if not games:
        return []
    
    query_norm = re.sub(r"[^a-z0-9]", "", query.lower())

    def score(game_name: str) -> int:
        name_norm = re.sub(r"[^a-z0-9]", "", game_name.lower())
        if query_norm == name_norm:
            return 1000
        if name_norm.startswith(query_norm):
            return 800 + (len(name_norm) - len(query_norm))
        if query_norm in name_norm:
            return 600 + (len(name_norm) - len(query_norm))
        chars = list(query_norm)
        score_val = 0
        for ch in name_norm:
            if chars and ch == chars[0]:
                score_val += 1
                chars.pop(0)
        if chars:
            return 0
        return max(0, score_val - abs(len(name_norm) - len(query_norm)))

    scored = [(score(g["name"]), g) for g in games if score(g["name"]) > 0]
    scored.sort(key=lambda x: (-x[0], x[1]["name"]))
    return [g for _, g in scored[:limit]]


def progressive_search(query: str, limit: int = 10) -> tuple[dict | None, list[dict]]:
    """
    If exact match fails, progressively shorten query by removing words.
    Returns: (best_match, other_suggestions)
    """
    words = query.split()
    if len(words) <= 1:
        return None, []
    
    checked: set[str] = set()
    suggestions: list[dict] = []
    
    for i in range(len(words), 0, -1):
        short_query = " ".join(words[:i])
        if not short_query or short_query in checked:
            continue
        checked.add(short_query)
        
        results = search_offline_games(short_query, limit=3)
        for r in results:
            if r["name"] not in [s["name"] for s in suggestions]:
                suggestions.append(r)
        
        if suggestions:
            break
    
    return suggestions[0] if suggestions else None, suggestions[1:]


def find_title_id(game_name: str, offline_only: bool = False) -> tuple[str | None, str | None]:
    """
    Find title ID for a game name.
    1. Try exact offline match
    2. Try progressive offline search  
    3. If not offline_only, try tinfoil online
    
    Returns (title_id, game_name).
    """
    offline_results = search_offline_games(game_name, limit=1)
    if offline_results:
        return offline_results[0]["title_id"], offline_results[0]["name"]
    
    if offline_only:
        result = progressive_search(game_name)
        if result[0]:
            return result[0]["title_id"], result[0]["name"]
        return None, None

    result = progressive_search(game_name)
    if result[0]:
        return result[0]["title_id"], result[0]["name"]

    _import_tinfoil()
    if tinfoil_search is None:
        return None, None
    
    entries = tinfoil_search.search_tinfoil(game_name, limit=5)
    if entries:
        return entries[0].title_id, entries[0].name
    
    words = game_name.split()
    if len(words) > 1:
        short_query = " ".join(words[:-1])
        entries = tinfoil_search.search_tinfoil(short_query, limit=3)
        if entries:
            return entries[0].title_id, entries[0].name

    return None, None


def search_with_confirmation(query: str) -> tuple[str | None, str | None]:
    """
    Interactive search that prompts user to confirm.
    
    1. Try exact offline match
    2. Try progressive offline (shorter queries)
    3. Try tinfoil online + progressive
    
    Returns (title_id, game_name) after user confirms, or (None, None) if cancelled.
    """
    results = search_offline_games(query, limit=5)
    if results:
        print(f"\nOffline matches for '{query}':")
        for i, r in enumerate(results, 1):
            print(f"  [{i}] {r['name']} [{r['title_id']}]")
        
        chosen = _prompt_choice(results, allow_online=False)
        if chosen:
            return chosen["title_id"], chosen["name"]
    
    result = progressive_search(query)
    if result[0]:
        print(f"\nProgressive offline: {result[0]['name']} [{result[0]['title_id']}]")
        if input("Use this? [y/n]: ").strip().lower() == "y":
            return result[0]["title_id"], result[0]["name"]
    
    _import_tinfoil()
    if tinfoil_search:
        entries = tinfoil_search.search_tinfoil(query, limit=5)
        if entries:
            print(f"\nOnline (tinfoil) matches:")
            for i, e in enumerate(entries, 1):
                print(f"  [{i}] {e.name} [{e.title_id}]")
            
            chosen = _prompt_choice_tinfoil(entries)
            if chosen:
                return chosen.title_id, chosen.name
        
        words = query.split()
        for i in range(len(words), 0, -1):
            short_query = " ".join(words[:i])
            if not short_query:
                continue
            entries = tinfoil_search.search_tinfoil(short_query, limit=3)
            if entries:
                print(f"\nOnline progressive '{short_query}':")
                for i, e in enumerate(entries, 1):
                    print(f"  [{i}] {e.name} [{e.title_id}]")
                chosen = _prompt_choice_tinfoil(entries)
                if chosen:
                    return chosen.title_id, chosen.name
                break
    
    return None, None


def _prompt_choice(results: list[dict], allow_online: bool = True) -> dict | None:
    if not results:
        return None
    if len(results) == 1:
        print(f"Using: {results[0]['name']} [{results[0]['title_id']}]")
        if input("Confirm? [y/n]: ").strip().lower() == "y":
            return results[0]
        return None
    
    print("[q] quit")
    if allow_online:
        print("[o] search online")
    
    while True:
        resp = input("Select: ").strip().lower()
        if resp == "q":
            return None
        if allow_online and resp == "o":
            return None
        try:
            idx = int(resp) - 1
            if 0 <= idx < len(results):
                return results[idx]
        except ValueError:
            pass


def _prompt_choice_tinfoil(entries):
    if not entries:
        return None
    if len(entries) == 1:
        print(f"Using: {entries[0].name} [{entries[0].title_id}]")
        if input("Confirm? [y/n]: ").strip().lower() == "y":
            return entries[0]
        return None
    
    print("[q] quit")
    print("[s] skip online search")
    
    while True:
        resp = input("Select: ").strip().lower()
        if resp == "q" or resp == "s":
            return None
        try:
            idx = int(resp) - 1
            if 0 <= idx < len(entries):
                return entries[idx]
        except ValueError:
            pass
    
    return None


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