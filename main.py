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


def extract_game_name_from_path(path: Path) -> tuple[str | None, str | None]:
    import re
    name = path.stem
    
    title_id_match = re.search(r"\[([0-9A-Fa-f]{16})\]", name)
    if title_id_match:
        return title_id_match.group(1).upper(), name
    
    junk_patterns = [
        r"\s*\[\s*[Xx][Cc][Ii]\s*\]",
        r"\s*\[\s*[Nn][Ss][Zz]\s*\]",
        r"\s*\[\s*[Nn][Ss][Pp]\s*\]",
        r"\s*\[\s*[Uu][Ss]\s*\]",
        r"\s*\[\s*[Ee][Uu]\s*\]",
        r"\s*\[\s*[Jj][Pp]\s*\]",
        r"\s*\[\s*[Kk][Oo][Rr]\s*\]",
        r"\s*\[\s*[Cc][Hh][Nn]\s*\]",
        r"\s*[\[0-9a-f]{16}\]",
        r"\s+v[0-9]+(\.[0-9]+)*\s*",
        r"\s+--\s*v[0-9]+\s*-",
        r"\s+_v[0-9]+\s*",
    ]
    for pattern in junk_patterns:
        try:
            name = re.sub(pattern, " ", name, flags=re.IGNORECASE)
        except re.error:
            pass
    
    name = name.replace("_", " ").replace("-", " ")
    name = re.sub(r"\s+", " ", name).strip()
    
    name = re.sub(r"\s+v\d+.*$", "", name, flags=re.IGNORECASE)
    
    common_suffixes = [" switch", " nsp", " xci", " nsx"]
    for suffix in common_suffixes:
        if name.lower().endswith(suffix):
            name = name[:-len(suffix)].strip()
    
    name = re.sub(r"\s+", " ", name).strip()
    
    if name and len(name) > 2:
        return None, name
    return None, None


def scan_roms_folder(folder_path: str) -> list[tuple[str | None, str]]:
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        return []

    games: list[tuple[str | None, str]] = []
    for item in folder.iterdir():
        if item.is_dir():
            title_id, name = extract_game_name_from_path(item)
            if name:
                games.append((title_id, name))
        elif item.is_file() and item.suffix.lower() in (".nsp", ".xci", ".nro", ".nsz", ".xcz"):
            title_id, name = extract_game_name_from_path(item)
            if name:
                games.append((title_id, name))

    return games


def find_title_id_for_game(game_name: str, offline_only: bool = False) -> tuple[str | None, str | None]:
    offline_results = search_offline_games(game_name, limit=1)
    if offline_results:
        return offline_results[0]["title_id"], offline_results[0]["name"]

    if offline_only:
        return None, None

    found_id = online_search(game_name)
    if found_id:
        return found_id, game_name

    return None, None


def process_games_folder(
    folder_path: str,
    output_dir: str,
    extended: bool,
    offline_only: bool = False,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    print(f"Scanning folder: {folder_path}")
    games = scan_roms_folder(folder_path)
    if not games:
        print("No ROM folders or files found.")
        return [], []

    print(f"Found {len(games)} items. Searching and generating...")

    success: list[tuple[str, str, str]] = []  # (title_id, game_name, output_folder)
    skipped: list[tuple[str, str]] = []  # (game_name, reason)

    for i, (title_id, name) in enumerate(games, 1):
        print(f"[{i}/{len(games)}] {name} ...", end=" ", flush=True)

        if not title_id:
            result = find_title_id_for_game(name, offline_only)
            title_id, found_name = result[0], result[1]

        if not title_id:
            print(f"skip (not found)")
            skipped.append((name, "not found"))
            continue

        cmd = [sys.executable, str(GENERATOR_SCRIPT), title_id, "-o", output_dir]
        if extended:
            cmd.append("-e")
        result = subprocess.run(
            cmd,
            cwd=SCRIPT_DIR,
            capture_output=True,
        )

        if result.returncode == 0:
            output = result.stdout.decode() if isinstance(result.stdout, bytes) else result.stdout
            if "Files written:" in output:
                count_line = [l for l in output.splitlines() if "Files written:" in l]
                if count_line and not count_line[0].startswith("Files written: 0"):
                    print(f"OK ({title_id})")
                    success.append((title_id, name, output_dir))
                    continue
        print(f"skip (no cheats)")
        skipped.append((name, "no cheats" if result.returncode != 0 else "failed"))

    return success, skipped


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
        help="Switch title ID (16 hex chars), game name, or folder path.",
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
        success, skipped = process_games_folder(
            args.games_folder,
            args.output_dir,
            args.extended,
            args.offline_only,
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