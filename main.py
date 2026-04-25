#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent.resolve()
GAMES_JSON = SCRIPT_DIR / "data" / "games.json"
SEARCH_SCRIPT = SCRIPT_DIR / "scripts" / "search.py"
GENERATOR_SCRIPT = SCRIPT_DIR / "scripts" / "generator.py"


def is_title_id(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9A-Fa-f]{16}", value.strip()))


def load_offline_games() -> list[dict]:
    if not GAMES_JSON.exists():
        return []
    try:
        return json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    except Exception:
        return []


def search_offline_games(query: str, limit: int = 10) -> list[dict]:
    games = load_offline_games()
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


def prompt_offline_choice(games: list[dict]) -> dict | None:
    if not games:
        return None
    if len(games) == 1:
        print(f"Offline: {games[0]['name']} [{games[0]['title_id']}]")
        return games[0]

    print("\nOffline matches:\n")
    for i, g in enumerate(games, 1):
        versions_note = f" ({g['version_count']} versions)" if g.get("version_count", 1) > 1 else ""
        print(f"  [{i}] {g['name']}{versions_note} [{g['title_id']}]")
    print("  [o] search online instead")
    print("  [q] quit")

    while True:
        resp = input("\nSelect a number: ").strip().lower()
        if resp == "q":
            return None
        if resp == "o":
            return None
        try:
            idx = int(resp) - 1
            if 0 <= idx < len(games):
                return games[idx]
        except ValueError:
            pass
        print("Please enter a number, 'o', or 'q'.")


def online_search(query: str) -> str | None:
    if not SEARCH_SCRIPT.exists():
        print("error: search.py not found", file=sys.stderr)
        return None

    try:
        result = subprocess.run(
            [sys.executable, str(SEARCH_SCRIPT), query, "-y", "--limit", "5"],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            input="y\n",
            encoding="utf-8",
            timeout=120,
        )
        for line in result.stdout.splitlines():
            if line.startswith("0100") and len(line) >= 16:
                return line[:16].strip()
        for line in result.stdout.splitlines():
            if line.startswith("Title ID:"):
                return line.split(":", 1)[1].strip()
    except Exception as exc:
        print(f"Online search failed: {exc}", file=sys.stderr)

    return None


def run_generator(title_id: str, output_dir: str, extended: bool = False) -> int:
    if not GENERATOR_SCRIPT.exists():
        print("error: generator.py not found", file=sys.stderr)
        return 1

    args = [sys.executable, str(GENERATOR_SCRIPT), title_id, "-o", output_dir]
    if extended:
        args.append("--extended")

    result = subprocess.run(args, cwd=SCRIPT_DIR)
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Switch emulator cheats from a title ID or game name.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Switch title ID (16 hex chars) or game name to search for.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="cheats",
        help="Output directory for generated cheats. Default: %(default)s",
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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    user_input = args.input.strip()

    if is_title_id(user_input):
        title_id = user_input.upper()
        print(f"Title ID: {title_id}")
        if args.search:
            return 0
        return run_generator(title_id, args.output_dir, args.extended)

    print(f'Searching for: "{user_input}"')
    offline_results = search_offline_games(user_input)

    if offline_results:
        chosen = prompt_offline_choice(offline_results)
        if chosen:
            title_id = chosen["title_id"]
            print(f"\nSelected: {chosen['name']}")
            print(f"Title ID: {title_id}")
            if args.search:
                return 0
            return run_generator(title_id, args.output_dir, args.extended)
    else:
        print("No offline matches found.")

    if args.offline_only:
        print("\nNo match in offline database. Provide the title ID directly for better results:")
        print(f"  python3 cheats.py <TITLE_ID>")
        return 1

    print("\nSearching online...")
    found_id = online_search(user_input)

    if found_id:
        title_id = found_id.upper()
        print(f"Found online: {title_id}")
        if args.search:
            return 0
        return run_generator(title_id, args.output_dir, args.extended)

    print("\nNo match found online either.")
    print(f"\nPlease provide the title ID directly:")
    print(f"  python3 cheats.py <TITLE_ID>")
    print(f"\nOr search manually at: https://tinfoil.io/Title/")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())