# Scripts

Helper modules for searching and generating cheats.

## scripts/search.py

Offline + online search functions.

### Functions

```python
from scripts.search import (
    find_title_id,           # Find Title ID for game name
    search_offline_games,    # Search offline database
    search_with_confirmation, # Interactive search with user prompts
)
```

#### find_title_id(game_name, offline_only=False)

Find Title ID for a game name.

```python
# Returns (title_id, game_name) or (None, None)
title_id, name = find_title_id("Mario Kart 8 Deluxe")
# ('0100152000022000', 'Mario Kart™ 8 Deluxe')
```

Search order:
1. Exact match in offline database (games.json)
2. If not offline_only, tinfoil online with progressive shortening

#### search_offline_games(query, limit=10)

Search offline database.

```python
results = search_offline_games("mario", limit=5)
# [{'title_id': '...', 'name': '...', ...}, ...]
```

#### search_with_confirmation(query)

Interactive search with user prompts.

```python
title_id, name = search_with_confirmation("mario kart")
# Shows results, prompts user to pick
```

## scripts/tinfoil_search.py

Online search via tinfoil.io API.

### Functions

```python
import scripts.tinfoil_search as tinfoil_search
```

#### search_tinfoil(query, limit=10)

Search tinfoil.io.

```python
entries = tinfoil_search.search_tinfoil("mario kart")
for e in entries:
    print(e.name, e.title_id)
```

#### find_title_by_id(title_id)

Get game name from Title ID.

```python
name = tinfoil_search.find_title_by_id("0100152000022000")
# 'Mario Kart™ 8 Deluxe'
```

#### fetch_all_tinfoil_titles()

Fetch all titles from tinfoil (for rebuilding DB).

```python
entries = tinfoil_search.fetch_all_tinfoil_titles()
print(f"Found {len(entries)} titles")
```

## scripts/generator.py

Core cheat code generator from tinfoil.io.

### Usage

```python
from scripts.generator import generate_cheats

generate_cheats(title_id, output_dir="cheats", extended=False)
```

### Output

Creates folder structure:
```
<output_dir>/<game_name>/<title_id>/<cheat_name>/Cheats/<build_id>.txt
```

## Command Line Usage

```bash
# Search only
python3 -c "from scripts.search import find_title_id; print(find_title_id('mario kart'))"

# Rebuild offline DB
python3 -c "from scripts.tinfoil_search import fetch_all_tinfoil_titles; ..."

# Generate by title ID
python3 scripts/generator.py 0100152000022000
```