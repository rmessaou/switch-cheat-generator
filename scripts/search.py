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
        region = re.sub(r"<[^>]+>", "", cells[2]).strip()
        version_match = re.search(r"(\d+)", cells[3])
        version_count = int(version_match.group(1)) if version_match else 0

        entries.append(GameEntry(title_id=title_id, name=name, region=region, version_count=version_count))

    return entries


def load_cache() -> list[GameEntry] | None:
    if not CACHE_FILE.exists():
        return None
    try:
        import time
        if time.time() - CACHE_FILE.stat().st_mtime < CACHE_MAX_AGE_DAYS * 86400:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            return [GameEntry(**d) for d in data]
    except Exception:
        pass
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


def find_title_id(game_name: str, offline_only: bool = False, auto: bool = False) -> tuple[str | None, str | None]:
    """
    Find title ID for a game name.
    
    1. Exact offline match
    2. If not offline_only, try tinfoil online full query -> progressively shorter
    
    If auto=False (default), prompts user when multiple offline matches.
    If auto=True or offline_only, auto-selects best match.
    """
    offline_results = search_offline_games(game_name, limit=1)
    if offline_results:
        return offline_results[0]["title_id"], offline_results[0]["name"]
    
    if offline_only:
        return None, None

    _import_tinfoil()
    if tinfoil_search is None:
        return None, None
    
    words = game_name.split()
    for i in range(len(words), 0, -1):
        short_query = " ".join(words[:i])
        if not short_query:
            continue
        entries = tinfoil_search.search_tinfoil(short_query, limit=3)
        if entries:
            if auto:
                return entries[0].title_id, entries[0].name
            
            print(f"  Found: {entries[0].name} [{entries[0].title_id}]")
            if len(entries) > 1:
                print("  Other matches:")
                for j, e in enumerate(entries[1:], 1):
                    print(f"    [{j}] {e.name} [{e.title_id}]")
            
            confirm = input("  Use this? [y/n]: ").strip().lower()
            if confirm == "y":
                return entries[0].title_id, entries[0].name
            return None, None
    
    return None, None


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
    if not entries:
        return []

    scored = [(fuzzy_score(query, e.name), e) for e in entries if fuzzy_score(query, e.name) > 0]
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:limit]]


def prompt_choice(entries: list[GameEntry], skip_confirm: bool = False) -> GameEntry | None:
    if not entries:
        return None
    if len(entries) == 1:
        print(f"Offline: {entries[0].name} [{entries[0].title_id}]")
        if skip_confirm:
            return entries[0]
        resp = input("Use this? [y/n]: ").strip().lower()
        return entries[0] if resp == "y" else None

    print("\nOffline matches:\n")
    for i, e in enumerate(entries, 1):
        print(f"  [{i}] {e.name} [{e.title_id}]")
    print("[q] quit")

    while True:
        resp = input("Select: ").strip().lower()
        if resp == "q":
            return None
        try:
            idx = int(resp) - 1
            if 0 <= idx < len(entries):
                return entries[idx]
        except ValueError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Switch emulator cheats from a title ID or game name.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Switch title ID or game name",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="cheats",
        help="Output directory. Default: cheats",
    )
    parser.add_argument(
        "-e", "--extended",
        action="store_true",
        help="Enable extended mode to fill missing build versions.",
    )
    parser.add_argument(
        "--offline-only",
        action="store_true",
        help="Only search the offline games.json, skip online search.",
    )
    parser.add_argument(
        "-s", "--search",
        action="store_true",
        help="Only search and display title ID without generating cheats.",
    )
    parser.add_argument(
        "-a", "--auto",
        action="store_true",
        help="Auto-select best match without prompting (for batch scripts).",
    )
    parser.add_argument(
        "-g", "--games-folder",
        metavar="PATH",
        help="Folder with ROM folders/files. Scans, searches, generates cheats for found games.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.games_folder:
        from main import process_games_folder
        success, skipped = process_games_folder(
            args.games_folder,
            args.output_dir,
            args.extended,
            args.offline_only,
            args.auto,
        )
        print(f"\n{'='*50}")
        print(f"Generated: {len(success)}")
        print(f"Skipped: {len(skipped)}")
        print(f"\nOutput folder: {args.output_dir}/")
        print(f"\nCopy '{args.output_dir}' folder to your emulator's mod/cheat directory.")
        return 0

    user_input = args.input.strip()

    if is_title_id(user_input):
        title_id = user_input.upper()
        print(f"Title ID: {title_id}")
        if args.search:
            return 0
        from main import run_generator
        return run_generator(title_id, args.output_dir, args.extended)

    print(f'Searching for: "{user_input}"')
    from main import run_generator
    offline_results = search_offline_games(user_input)

    if offline_results:
        chosen = prompt_choice([GameEntry(**r) for r in offline_results], skip_confirm=args.auto)
        if chosen:
            title_id = chosen.title_id
            print(f"\nSelected: {chosen.name}")
            print(f"Title ID: {title_id}")
            if args.search:
                return 0
            return run_generator(title_id, args.output_dir, args.extended)
    else:
        print("No offline matches found.")

    if args.offline_only:
        print("\nNo match in offline database. Provide the title ID directly:")
        print(f"  python3 main.py <TITLE_ID>")
        return 1

    print("\nSearching online...")
    from main import is_title_id
    result = find_title_id(user_input, auto=args.auto)

    if result[0]:
        title_id = result[0]
        print(f"Found online: {title_id}")
        print(f"Game: {result[1]}")
        if args.search:
            return 0
        return run_generator(title_id, args.output_dir, args.extended)

    print("\nNo match found.")
    print(f"\nProvide the title ID directly:")
    print(f"  python3 main.py <TITLE_ID>")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())