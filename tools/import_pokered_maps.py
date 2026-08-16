"""Generate the canonical Red/Blue map registry from pret/pokered constants.

Usage:
    python tools/import_pokered_maps.py SOURCE_ASM OUTPUT_PY COMMIT_SHA
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path


MAP_PATTERN = re.compile(
    r"^\s*map_const\s+([A-Z0-9_]+),\s*(\d+),\s*(\d+)\s*;\s*\$([0-9A-Fa-f]{2})(?:\s*;.*)?$"
)


def display_name(symbol: str) -> str:
    replacements = {
        "POKEMON": "Pokémon",
        "POKECENTER": "Pokémon Center",
        "MT": "Mt.",
        "MR": "Mr.",
        "SS": "S.S.",
        "REDS": "Red's",
        "BLUES": "Blue's",
        "OAKS": "Oak's",
        "BILLS": "Bill's",
        "DIGLETTS": "Diglett's",
        "LANCES": "Lance's",
        "LORELEIS": "Lorelei's",
        "BRUNOS": "Bruno's",
        "AGATHAS": "Agatha's",
        "CAPTAINS": "Captain's",
        "WARDENS": "Warden's",
        "FUJIS": "Fuji's",
        "PSYCHICS": "Psychic's",
        "NAME": "Name",
        "RATERS": "Rater's",
    }
    words = []
    for token in symbol.split("_"):
        if token in replacements:
            words.append(replacements[token])
        elif re.fullmatch(r"(?:B|[1-9]\d*)\d*F", token) or token in {"1F", "2F", "3F"}:
            words.append(token)
        else:
            words.append(token.title())
    return " ".join(words)


def parse_maps(source: str) -> list[tuple[int, str, int, int]]:
    maps: list[tuple[int, str, int, int]] = []
    for line in source.splitlines():
        match = MAP_PATTERN.match(line)
        if not match:
            continue
        symbol, width, height, hexadecimal_id = match.groups()
        map_id = int(hexadecimal_id, 16)
        if map_id != len(maps):
            raise ValueError(f"Map sequence mismatch: expected {len(maps):#04x}, got {map_id:#04x}")
        maps.append((map_id, symbol, int(width), int(height)))
    if len(maps) != 248:
        raise ValueError(f"Expected 248 Red/Blue maps, found {len(maps)}")
    return maps


def render(source: bytes, commit_sha: str) -> str:
    maps = parse_maps(source.decode("utf-8"))
    source_hash = hashlib.sha256(source).hexdigest()
    lines = [
        '"""Generated canonical Pokémon Red/Blue map registry. Do not edit by hand."""',
        "",
        "from dataclasses import dataclass",
        "",
        f'POKERED_COMMIT = "{commit_sha}"',
        f'POKERED_MAP_CONSTANTS_SHA256 = "{source_hash}"',
        "",
        "@dataclass(frozen=True)",
        "class MapDefinition:",
        "    map_id: int",
        "    stable_id: str",
        "    display_name: str",
        "    width_blocks: int",
        "    height_blocks: int",
        "    is_unused: bool",
        "",
        "MAPS = {",
    ]
    for map_id, symbol, width, height in maps:
        lines.append(
            f'    0x{map_id:02X}: MapDefinition(0x{map_id:02X}, "{symbol.lower()}", '
            f'"{display_name(symbol)}", {width}, {height}, {symbol.startswith("UNUSED_MAP_")}),'
        )
    lines.extend([
        "}",
        "",
        "def get_map(map_id: int) -> MapDefinition | None:",
        "    return MAPS.get(map_id)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: import_pokered_maps.py SOURCE_ASM OUTPUT_PY COMMIT_SHA")
    source_path, output_path, commit_sha = map(Path, sys.argv[1:])
    output_path.write_text(render(source_path.read_bytes(), str(commit_sha)), encoding="utf-8")


if __name__ == "__main__":
    main()
