# switch_emu_cheat_codes

Generate Switch emulator cheat files from a Tinfoil title page.

The generated folder structure is compatible with Yuzu, Citron, Sudachi, and other Switch emulators or tools that resolve cheats by Build ID using the same general layout.

The script scrapes cheats from `https://tinfoil.io/Title/<TITLE_ID>`, groups them by cheat name and Tinfoil version labels like `v9`, matches those versions to the page's Build ID table, and writes files in this shape:

```text
cheats/<game_name>/<title_id>/<cheat_name>/Cheats/<build_id>.txt
```

Each `.txt` contains only that cheat's block, so users can browse by cheat name and still get the correct file for their installed build. Cheats are divided by name to make activation and deactivation easier inside emulator cheat managers.

## Usage

The script expects a Switch title ID as input.

You can usually find the title ID:

- in your emulator's game information or properties view
- by searching for the game on `https://tinfoil.io/Title/`

Once you have the title ID, run the script like this:

Run with a title ID:

```bash
python3 generator.py 0100152000022000
```

Or with a full Tinfoil URL:

```bash
python3 generator.py https://tinfoil.io/Title/0100152000022000
```

Write somewhere else:

```bash
python3 generator.py 0100152000022000 --output-dir output
```

Enable version fan-out for missing builds:

```bash
python3 generator.py 0100152000022000 --extended
```

## Output

For a title page that contains cheats and build IDs, the script creates one folder per cheat name, then one file per mapped build ID for that cheat.

Example:

```text
cheats/
  Mario Kart 8 Deluxe/
    0100152000022000/
      Infinite Health/
        Cheats/
          FE1B230800D4933C.txt
```

## Extended Mode

With `--extended`, if a cheat exists for at least one mapped version, the script also writes that cheat to every missing known build ID for the title.

This option was added because Tinfoil sometimes lists a cheat under only one or a few versions even when the cheat may still work on other builds. `--extended` fills those missing Build ID files so that if a user imports the generated folder into an emulator, they are more likely to always see a usable cheat regardless of the installed game version.

When `--extended` is not used, the generator only writes builds that can be mapped directly from the title page data.

## Notes

- The script uses only the Python standard library.
- Tinfoil pages sometimes contain duplicate or malformed cheat rows. The generator preserves the page data as-is instead of trying to invent fixes.
- If a cheat version exists on the page but there is no matching Build ID row, that cheat/version pair is skipped and reported as a warning.
- Folder names are sanitized for Windows-safe paths.
- Cheat names are split into separate folders so individual cheats are easier to browse, enable, and disable.
- In `--extended` mode, missing build files reuse the first mapped cheat variant found for that cheat.
