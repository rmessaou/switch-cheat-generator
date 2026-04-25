# switch_emu_cheat_codes

Generate Switch emulator cheat files from a Tinfoil title page.

The generated folder structure is compatible with Yuzu, Citron, Sudachi, and other Switch emulators or tools that resolve cheats by Build ID using the same general layout.

## Quick Start

The main entry point is `main.py`. It can accept either a title ID or a game name:

```bash
# With title ID
python3 main.py 0100152000022000

# With game name (searches offline then online)
python3 main.py "mario kart"

# Search only, no generation
python3 main.py "mario kart" -s
```

## Usage

The main script (`main.py`) accepts:

- A Switch title ID (16 hex characters)
- A game name (searches offline database, falls back to online)

Find the title ID in your emulator's game info/properties, or search manually at `https://tinfoil.io/Title/`.

### Options

```bash
python3 main.py <input> [options]

input                   Switch title ID or game name
-o, --output-dir DIR    Output directory (default: cheats)
-e, --extended        Fill missing build versions
--offline-only        Skip online search
-s, --search         Only search, don't generate
```

### Examples

```bash
# Generate cheats by title ID
python3 main.py 0100152000022000

# Search by name and generate
python3 main.py "mario kart"

# Search only (find title ID)
python3 main.py "mario kart" -s

# Extended mode (fill all builds)
python3 main.py 0100152000022000 -e

# Custom output folder
python3 main.py 0100152000022000 -o my_cheats
```

## Output

The script creates:

```text
cheats/<game_name>/<title_id>/<cheat_name>/Cheats/<build_id>.txt
```

Each `.txt` contains only that cheat's block. Cheats are split by name for easier enable/disable.

## Extended Mode

With `--extended`, if a cheat exists for at least one mapped version, the script also writes that cheat to every known build ID for the title. This fills gaps when Tinfoil under-lists versions.

## Offline Database

The `data/games.json` contains ~2,300 game titles for offline searching. Search is fast without network.

To update the offline database:

```bash
python3 -c "import search; search.fetch_entries()"
```

## Files

```
.
├── main.py              # Main entry point
├── README.md           # This file
├── cheats/            # Generated cheats output
├── data/
│   └── games.json     # Offline title database
└── scripts/
    ├── generator.py  # Core generator
    └── search.py    # Online search helper
```

## Notes

- Only Python standard library required.
- Folder names are sanitized for Windows compatibility.
- When no cheats exist, check manually at `https://tinfoil.io/Title/<TITLE_ID>`