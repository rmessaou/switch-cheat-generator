#!/usr/bin/env python3

from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


TITLE_BASE_URL = "https://tinfoil.io/Title/"


@dataclass
class CheatEntry:
    name: str
    version: str
    lines: list[str]


def clean_html_text(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def headerize(name: str) -> str:
    inner = normalize_cheat_label(name)
    return f"[{inner}]"


def sanitize_path_part(value: str, fallback: str) -> str:
    sanitized = strip_wrapping_brackets(value)
    sanitized = sanitized.encode("ascii", errors="ignore").decode("ascii")
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f\[\]{}()@#~`!$%^&=+;,]', "_", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip().rstrip(".")
    sanitized = re.sub(r"_+", "_", sanitized)
    sanitized = sanitized.strip(" _-")
    return sanitized or fallback


def strip_wrapping_brackets(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped[1:-1].strip()
    return stripped


def normalize_cheat_label(value: str) -> str:
    normalized = strip_wrapping_brackets(value)
    normalized = normalized.encode("ascii", errors="ignore").decode("ascii")
    normalized = re.sub(r"[\x00-\x1f]", " ", normalized)
    normalized = re.sub(r"[{}()@#~`!$%^&=+;,]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or "unnamed_cheat"


def extract_title_id(value: str) -> str:
    match = re.search(r"([0-9A-Fa-f]{16})", value)
    if not match:
        raise ValueError("Expected a 16-character Switch title ID or a Tinfoil title URL.")
    return match.group(1).upper()


def title_url(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return value
    return urllib.parse.urljoin(TITLE_BASE_URL, extract_title_id(value))


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "switch-emu-cheat-codes/0.1 (+https://tinfoil.io/Title/)"
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def parse_game_name(document: str, fallback: str) -> str:
    match = re.search(r"<h1>\s*(.*?)\s*</h1>", document, flags=re.IGNORECASE | re.DOTALL)
    if match:
        name = clean_html_text(match.group(1))
        if name and name.lower() != "titles":
            return name
    title_match = re.search(r"<title>\s*(.*?)\s*</title>", document, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        page_title = clean_html_text(title_match.group(1)).replace("| Tinfoil", "").strip(" -")
        if page_title:
            return page_title
    return fallback


def parse_build_ids(document: str) -> dict[str, str]:
    section_match = re.search(
        r"<h2>\s*Build ID'?s\s*</h2>(.*?)</table>",
        document,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not section_match:
        return {}

    build_ids: dict[str, str] = {}
    for build_id, version in re.findall(
        r"<tr>\s*<td>\s*([0-9A-Fa-f]{16,64})\s*</td>\s*<td>\s*(v\d+)\s*</td>\s*</tr>",
        section_match.group(1),
        flags=re.IGNORECASE | re.DOTALL,
    ):
        build_ids[version.lower()] = build_id[:16].upper()
    return build_ids


def parse_cheats(document: str) -> dict[str, list[CheatEntry]]:
    grouped: dict[str, list[CheatEntry]] = defaultdict(list)

    for row in re.findall(r"<tr>(.*?)</tr>", document, flags=re.IGNORECASE | re.DOTALL):
        if "<ul class=\"cheat fixed\"" not in row:
            continue

        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.IGNORECASE | re.DOTALL)
        if len(cells) < 4:
            continue

        name = clean_html_text(cells[0])
        version = clean_html_text(cells[1]).lower()
        lines = [clean_html_text(item) for item in re.findall(r"<li>(.*?)</li>", cells[3], flags=re.IGNORECASE | re.DOTALL)]
        lines = [line for line in lines if line]

        if not name or not version or not lines:
            continue

        grouped[version].append(CheatEntry(name=name, version=version, lines=lines))

    return dict(grouped)


def version_sort_key(value: str) -> int:
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else -1


def group_cheats_by_name(cheats_by_version: dict[str, list[CheatEntry]]) -> dict[str, dict[str, list[CheatEntry]]]:
    grouped: dict[str, dict[str, list[CheatEntry]]] = defaultdict(lambda: defaultdict(list))
    for version, entries in cheats_by_version.items():
        for entry in entries:
            grouped[entry.name][version].append(entry)
    return {name: dict(version_map) for name, version_map in grouped.items()}


def render_cheat_file(entries: list[CheatEntry]) -> str:
    chunks: list[str] = []
    for entry in entries:
        chunks.append(headerize(entry.name))
        chunks.extend(entry.lines)
        chunks.append("")
    return "\n".join(chunks).rstrip() + "\n"


def build_cheat_versions(
    entries_by_version: dict[str, list[CheatEntry]],
    build_ids: dict[str, str],
    extended: bool,
) -> tuple[dict[str, list[CheatEntry]], list[str]]:
    resolved: dict[str, list[CheatEntry]] = {}
    warnings: list[str] = []
    unmapped_entries: list[CheatEntry] = []

    for version, entries in entries_by_version.items():
        build_id = build_ids.get(version)
        if not build_id:
            if extended:
                unmapped_entries.extend(entries)
            else:
                warnings.append(f"Skipped {entries[0].name} for {version}: no build ID listed on the title page.")
            continue
        resolved[build_id] = entries

    if extended and resolved:
        fallback_entries = next(iter(resolved.values()))
        for build_id in build_ids.values():
            resolved.setdefault(build_id, fallback_entries)

    if extended and unmapped_entries and not resolved:
        for build_id in build_ids.values():
            resolved.setdefault(build_id, unmapped_entries)

    if extended and unmapped_entries and resolved:
        fallback_entries = next(iter(resolved.values()))
        for build_id in build_ids.values():
            resolved.setdefault(build_id, fallback_entries)

    return resolved, warnings


def write_outputs(
    output_root: Path,
    game_name: str,
    title_id: str,
    cheats_by_version: dict[str, list[CheatEntry]],
    build_ids: dict[str, str],
    extended: bool,
) -> tuple[list[Path], list[str]]:
    written: list[Path] = []
    warnings: list[str] = []
    game_dir = output_root / sanitize_path_part(game_name, title_id) / title_id
    cheats_by_name = group_cheats_by_name(cheats_by_version)

    for cheat_name in sorted(cheats_by_name):
        resolved_versions, cheat_warnings = build_cheat_versions(cheats_by_name[cheat_name], build_ids, extended)
        warnings.extend(cheat_warnings)

        if not resolved_versions:
            continue

        cheat_dir = game_dir / sanitize_path_part(cheat_name, "unnamed_cheat") / "Cheats"
        cheat_dir.mkdir(parents=True, exist_ok=True)

        for build_id, entries in sorted(resolved_versions.items()):
            output_file = cheat_dir / f"{build_id}.txt"
            output_file.write_text(render_cheat_file(entries), encoding="utf-8")
            written.append(output_file)

    return written, warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch cheats from a Tinfoil title page and generate emulator cheat files.",
    )
    parser.add_argument(
        "title",
        help="Switch title ID (for example 0100152000022000) or full Tinfoil title URL.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="cheats",
        help="Root directory where generated cheat folders will be written. Default: %(default)s",
    )
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Fill every missing build for a cheat by reusing one mapped cheat version for that game.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        title_id = extract_title_id(args.title)
        url = title_url(args.title)
        document = fetch_html(url)
        game_name = parse_game_name(document, title_id)
        build_ids = parse_build_ids(document)
        cheats_by_version = parse_cheats(document)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except urllib.error.URLError as exc:
        print(f"error: failed to fetch {args.title}: {exc}", file=sys.stderr)
        return 1

    if not cheats_by_version:
        print(f"No cheats found for {title_id} ({game_name}).", file=sys.stderr)
        print(f"\nCheck manually at: https://tinfoil.io/Title/{title_id}", file=sys.stderr)
        return 1

    written, warnings = write_outputs(
        Path(args.output_dir),
        game_name,
        title_id,
        cheats_by_version,
        build_ids,
        args.extended,
    )

    print(f"Game: {game_name}")
    print(f"Title ID: {title_id}")
    print(f"Cheat versions found: {len(cheats_by_version)}")
    print(f"Extended mode: {'on' if args.extended else 'off'}")
    print(f"Files written: {len(written)}")

    for path in written:
        print(f"  - {path}")

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
