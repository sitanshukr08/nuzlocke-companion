"""Generate canonical Red/Blue move, type, and species base-data registries."""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path


CONST_PATTERN = re.compile(r"^\s*const\s+([A-Z0-9_]+)\s*;\s*\$?([0-9A-Fa-f]+)\s*$")
MOVE_PATTERN = re.compile(
    r"^\s*move\s+([A-Z0-9_]+),\s*([A-Z0-9_]+),\s*(\d+),\s*([A-Z0-9_]+),\s*(\d+),\s*(\d+)\s*$"
)


def constants(path: Path, *, base: int, prefix: str | None = None) -> dict[str, int]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = CONST_PATTERN.match(line)
        if match and (prefix is None or match.group(1).startswith(prefix)):
            result[match.group(1)] = int(match.group(2), base)
    return result


def stable(symbol: str) -> str:
    return symbol.removesuffix("_TYPE").lower()


def display(symbol: str) -> str:
    special = {
        "MR_MIME": "Mr. Mime",
        "FARFETCHD": "Farfetch'd",
        "NIDORAN_F": "Nidoran♀",
        "NIDORAN_M": "Nidoran♂",
        "PSYCHIC_M": "Psychic",
        "PSYCHIC_TYPE": "Psychic",
        "HI_JUMP_KICK": "Hi Jump Kick",
    }
    return special.get(symbol, symbol.replace("_", " ").title())


def parse_types(root: Path) -> dict[str, int]:
    return constants(root / "constants/type_constants.asm", base=16)


def parse_moves(root: Path, types: dict[str, int]) -> list[dict[str, object]]:
    move_ids = constants(root / "constants/move_constants.asm", base=16)
    move_ids.pop("NO_MOVE", None)
    names = re.findall(r'^\s*li\s+"([^"]+)"', (root / "data/moves/names.asm").read_text(encoding="utf-8"), re.M)
    characteristics = {}
    for line in (root / "data/moves/moves.asm").read_text(encoding="utf-8").splitlines():
        match = MOVE_PATTERN.match(line)
        if match:
            symbol, effect, power, type_symbol, accuracy, pp = match.groups()
            characteristics[symbol] = (effect, int(power), type_symbol, int(accuracy), int(pp))
    if len(move_ids) != 165 or len(names) != 165 or len(characteristics) != 165:
        raise ValueError(
            f"Expected 165 moves, got ids={len(move_ids)}, names={len(names)}, data={len(characteristics)}"
        )
    moves = []
    for symbol, move_id in sorted(move_ids.items(), key=lambda item: item[1]):
        effect, power, type_symbol, accuracy, pp = characteristics[symbol]
        moves.append({
            "move_id": move_id,
            "stable_id": stable(symbol),
            "display_name": names[move_id - 1].title(),
            "power": power,
            "type_id": types[type_symbol],
            "accuracy_percent": accuracy,
            "base_pp": pp,
            "effect_id": stable(effect),
        })
    return moves


def parse_species(root: Path, types: dict[str, int]) -> list[dict[str, object]]:
    pokemon_ids = constants(root / "constants/pokemon_constants.asm", base=16)
    pokemon_ids.pop("NO_MON", None)
    real_ids = {symbol: value for symbol, value in pokemon_ids.items() if value <= 0xBE}
    dex_ids = constants(root / "constants/pokedex_constants.asm", base=10, prefix="DEX_")
    dex_to_internal = {
        dex_ids[f"DEX_{symbol}"]: internal_id
        for symbol, internal_id in real_ids.items()
        if f"DEX_{symbol}" in dex_ids
    }
    growth_names = {
        "GROWTH_MEDIUM_FAST": "medium_fast",
        "GROWTH_SLIGHTLY_FAST": "slightly_fast",
        "GROWTH_SLIGHTLY_SLOW": "slightly_slow",
        "GROWTH_MEDIUM_SLOW": "medium_slow",
        "GROWTH_FAST": "fast",
        "GROWTH_SLOW": "slow",
    }
    species = []
    for path in sorted((root / "data/pokemon/base_stats").glob("*.asm")):
        text = path.read_text(encoding="utf-8")
        dex_match = re.search(r"^\s*db\s+DEX_([A-Z0-9_]+)\s*;", text, re.M)
        stat_match = re.search(r"^\s*db\s+(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*$", text, re.M)
        type_match = re.search(r"^\s*db\s+([A-Z0-9_]+),\s*([A-Z0-9_]+)\s*;\s*type", text, re.M)
        growth_match = re.search(r"^\s*db\s+(GROWTH_[A-Z_]+)\s*;\s*growth rate", text, re.M)
        if not all((dex_match, stat_match, type_match, growth_match)):
            raise ValueError(f"Could not parse base stats from {path}")
        symbol = dex_match.group(1)
        dex_number = dex_ids[f"DEX_{symbol}"]
        internal_id = dex_to_internal[dex_number]
        hp, attack, defense, speed, special = map(int, stat_match.groups())
        type1, type2 = type_match.groups()
        species.append({
            "internal_id": internal_id,
            "dex_number": dex_number,
            "stable_id": stable(symbol),
            "display_name": display(symbol),
            "base_hp": hp,
            "base_attack": attack,
            "base_defense": defense,
            "base_speed": speed,
            "base_special": special,
            "type1_id": types[type1],
            "type2_id": types[type2],
            "growth_rate": growth_names[growth_match.group(1)],
        })
    if len(species) != 151 or len({item["internal_id"] for item in species}) != 151:
        raise ValueError(f"Expected 151 unique species, got {len(species)}")
    return sorted(species, key=lambda item: item["internal_id"])


def source_hash(root: Path, paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def render(root: Path, commit: str) -> str:
    types = parse_types(root)
    moves = parse_moves(root, types)
    species = parse_species(root, types)
    source_paths = [
        root / "constants/type_constants.asm",
        root / "constants/move_constants.asm",
        root / "constants/pokemon_constants.asm",
        root / "constants/pokedex_constants.asm",
        root / "data/moves/names.asm",
        root / "data/moves/moves.asm",
        *sorted((root / "data/pokemon/base_stats").glob("*.asm")),
    ]
    lines = [
        '"""Generated canonical Gen I battle data. Do not edit by hand."""',
        "",
        "from dataclasses import dataclass",
        "",
        f'POKERED_COMMIT = "{commit}"',
        f'POKERED_BATTLE_SOURCES_SHA256 = "{source_hash(root, source_paths)}"',
        "",
        "@dataclass(frozen=True)",
        "class TypeDefinition:",
        "    type_id: int",
        "    stable_id: str",
        "    display_name: str",
        "",
        "@dataclass(frozen=True)",
        "class MoveDefinition:",
        "    move_id: int",
        "    stable_id: str",
        "    display_name: str",
        "    power: int",
        "    type_id: int",
        "    accuracy_percent: int",
        "    base_pp: int",
        "    effect_id: str",
        "",
        "@dataclass(frozen=True)",
        "class SpeciesBaseData:",
        "    internal_id: int",
        "    dex_number: int",
        "    stable_id: str",
        "    display_name: str",
        "    base_hp: int",
        "    base_attack: int",
        "    base_defense: int",
        "    base_speed: int",
        "    base_special: int",
        "    type1_id: int",
        "    type2_id: int",
        "    growth_rate: str",
        "",
        "TYPES = {",
    ]
    for symbol, type_id in sorted(types.items(), key=lambda item: item[1]):
        lines.append(
            f'    0x{type_id:02X}: TypeDefinition(0x{type_id:02X}, "{stable(symbol)}", "{display(symbol)}"),'
        )
    lines.append("}")
    lines.append("")
    lines.append("MOVES = {")
    for item in moves:
        lines.append(
            "    0x{move_id:02X}: MoveDefinition(0x{move_id:02X}, {stable_id!r}, {display_name!r}, "
            "{power}, 0x{type_id:02X}, {accuracy_percent}, {base_pp}, {effect_id!r}),".format(**item)
        )
    lines.append("}")
    lines.append("")
    lines.append("SPECIES_BASE_DATA = {")
    for item in species:
        lines.append(
            "    0x{internal_id:02X}: SpeciesBaseData(0x{internal_id:02X}, {dex_number}, {stable_id!r}, "
            "{display_name!r}, {base_hp}, {base_attack}, {base_defense}, {base_speed}, {base_special}, "
            "0x{type1_id:02X}, 0x{type2_id:02X}, {growth_rate!r}),".format(**item)
        )
    lines.extend([
        "}",
        "",
        "def get_type(type_id: int) -> TypeDefinition | None:",
        "    return TYPES.get(type_id)",
        "",
        "def get_move(move_id: int) -> MoveDefinition | None:",
        "    return MOVES.get(move_id)",
        "",
        "def get_species_base_data(internal_id: int) -> SpeciesBaseData | None:",
        "    return SPECIES_BASE_DATA.get(internal_id)",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: import_pokered_battle_data.py POKERED_ROOT OUTPUT_PY COMMIT_SHA")
    root = Path(sys.argv[1])
    Path(sys.argv[2]).write_text(render(root, sys.argv[3]), encoding="utf-8")


if __name__ == "__main__":
    main()
