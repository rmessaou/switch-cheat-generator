#!/usr/bin/env python3

import json
import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).parent.parent.resolve()


def test_offline_search():
    result = subprocess.run(
        [sys.executable, "main.py", "mario kart", "-s"],
        cwd=REPO_DIR,
        input="2\n",
        capture_output=True,
        text=True,
    )
    print(f"DEBUG: returncode={result.returncode}")
    assert "0100152000022000" in result.stdout, f"Offline search failed: {result.stdout}"
    print("PASS: offline_search")


def test_title_id_direct():
    result = subprocess.run(
        [sys.executable, "main.py", "0100152000022000", "-o", "test_output"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Title ID generation failed: {result.stderr}"
    assert Path("test_output/Mario Kart 8 Deluxe").exists(), "Output not created"
    print("PASS: title_id_direct")


def test_extended_mode():
    result = subprocess.run(
        [sys.executable, "main.py", "0100152000022000", "-o", "test_output_ext", "-e"],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Extended mode failed: {result.stderr}"
    print("PASS: extended_mode")


def main() -> int:
    tests = [test_offline_search, test_title_id_direct, test_extended_mode]

    for test in tests:
        try:
            test()
        except AssertionError as exc:
            print(f"FAIL: {test.__name__} - {exc}")
            return 1
        except Exception as exc:
            print(f"ERROR: {test.__name__} - {exc}")
            return 1

    print("\nAll tests passed!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())