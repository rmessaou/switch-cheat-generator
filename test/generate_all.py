#!/usr/bin/env python3

import json
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).parent.parent.resolve()
DATA_DIR = REPO_DIR / "data"
GAMES_JSON = DATA_DIR / "games.json"


def main() -> int:
    games = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    print(f"Found {len(games)} games in database.")

    for i, game in enumerate(games, 1):
        title_id = game["title_id"]
        name = game["name"]
        print(f"[{i}/{len(games)}] Generating for: {name} ({title_id}) ..."),

        try:
            result = subprocess.run(
                [sys.executable, "main.py", title_id, "-o", "test_output", "-e"],
                cwd=REPO_DIR,
                capture_output=True,
                timeout=60,
            )
            if result.returncode == 0:
                print(" OK")
            elif "No cheats found" in result.stderr:
                print(" skipping (no cheats)")
            else:
                print(f" error: {result.stderr[:50]}")
        except Exception as exc:
            print(f" failed: {exc}")

    print("\nDone. Cheats generated in: test_output/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())