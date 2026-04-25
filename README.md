# switch-cheat-generator

Generate Switch emulator cheat files from tinfoil.io.

The generated folder structure is compatible with Yuzu, Sudachi, Ryujinx, and other Switch emulators.

## Quick Start

```bash
# By title ID
python3 main.py 0100152000022000

# By game name (searches offline first, then online)
python3 main.py "Mario Kart 8 Deluxe"

# Batch process a ROMs folder
python3 main.py --games-folder ROMs -o cheats
```

## main.py Options

```bash
python3 main.py <input> [options]

# Input options (one required):
  title_id            Switch title ID (16 hex chars) - e.g., 0100152000022000
  game_name          Game name to search

# Output options:
  -o, --output-dir DIR    Output directory (default: cheats)

# Search options:
  --offline-only        Only search offline database, skip online
  -s, --search       Search only, don't generate cheats

# Generator options:
  -e, --extended     Fill missing build versions

# Batch options:
  --games-folder DIR   Process all ROMs in folder
```

## Examples

```bash
# Generate cheats by title ID
python3 main.py 0100152000022000

# Search by name
python3 main.py "Mario Kart"

# Search only (find title ID)
python3 main.py "Mario Kart" -s

# Batch process ROMs folder
python3 main.py --games-folder ROMs -o my_cheats

# Extended mode (fill all builds)
python3 main.py 0100152000022000 -e
```

## --extended Mode

By default, cheats are written only for the builds that exist on tinfoil.io. But some games have cheats written for an older version that still work on newer versions.

With `--extended`, the generator copies each cheat to **all known build IDs** for that title. This ensures cheats work even if you're on a version not listed on tinfoil.

```bash
# Example: Mario Kart 8 Deluxe v1.7.1 cheats also work on v1.7.2, v2.0.0, etc.
python3 main.py 0100152000022000 -e
```

## Output Structure

```
cheats/<game_name>/<title_id>/<cheat_name>/Cheats/<build_id>.txt
```

Each `.txt` contains one cheat block. Cheats split by name for easy enable/disable.

Example:
```
cheats/Mario Kart 8 Deluxe/0100152000022000/Infinite Coins/Cheats/FE1B230800D4933C.txt
cheats/Mario Kart 8 Deluxe/0100152000022000/Infinite Coins/Cheats/068AE4992C45B028.txt
```

## Offline Database

`data/games.json` contains ~18,000 game titles from tinfoil.io for offline searching.

Search order:
1. Embedded Title ID in filename (e.g., `Game[0100152000022000].nsp`)
2. Offline exact match in games.json
3. Tinfoil online (progressively shorter query if needed)

## Requirements

- Python 3.10+
- No external packages required

## Notes

- Folder names sanitized for Windows
- When no cheats exist, check manually at https://tinfoil.io/Title/<TITLE_ID>
- ROM naming tips: include Title ID in brackets `[0100...]` for automatic detection