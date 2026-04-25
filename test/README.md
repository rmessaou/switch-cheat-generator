# Test Scripts

## test_functionality.py

Runs basic functionality tests:

- `test_offline_search` - searches offline database
- `test_title_id_direct` - generates cheats by title ID
- `test_extended_mode` - generates cheats with extended mode

Run with:
```bash
python3 test/test_functionality.py
```

## generate_all.py

Generates cheats for **all ~2,283 games** in the offline database using extended mode.

### Disk Space Estimate

Based on Mario Kart 8 Deluxe (134 files ~500KB):
- Average: ~30-50 cheats × ~10 builds = ~300 files/game
- Each file ~1-2KB → ~300-600KB/game
- **Extended mode:** doubles this (all build IDs)
- **2,283 games × ~500KB ≈ ~1.1 GB**

### Time Estimate

- Sequential processing (one game at a time)
- ~30-60 seconds per game (network + generation)
- **2,283 games × 45 seconds ≈ 28 hours** (worst case)
- **With cache:** ~10-15 seconds/game → ~6-10 hours

### Output

- Location: `test_output/` in repo root
- Structure: `test_output/<game_name>/<title_id>/<cheat_name>/Cheats/<build_id>.txt`
- Extended mode: includes all known build IDs per game

### Run (Not Recommended)

```bash
python3 test/generate_all.py
```

**Warning:** This will take many hours and use 1GB+ disk space.

### Alternative: Small Test

Generate cheats for just a few games:

```bash
python3 -c "
import json
import subprocess
from pathlib import Path

games = json.loads(Path('data/games.json').read_text())
for game in games[:5]:
    subprocess.run(['python3', 'main.py', game['title_id'], '-o', 'test_sample'], capture_output=True)
"
```