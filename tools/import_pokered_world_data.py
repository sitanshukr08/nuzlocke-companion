"""Generate canonical Red/Blue encounters, trainers, items, and map connections."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


SLOT_WEIGHTS = (51, 51, 39, 25, 25, 25, 13, 13, 11, 3)

BOSS_EVENTS = {
    ("PEWTER_GYM", "BROCK"): "EVENT_BEAT_BROCK",
    ("CERULEAN_GYM", "MISTY"): "EVENT_BEAT_MISTY",
    ("VERMILION_GYM", "LT_SURGE"): "EVENT_BEAT_LT_SURGE",
    ("CELADON_GYM", "ERIKA"): "EVENT_BEAT_ERIKA",
    ("FUCHSIA_GYM", "KOGA"): "EVENT_BEAT_KOGA",
    ("SAFFRON_GYM", "SABRINA"): "EVENT_BEAT_SABRINA",
    ("CINNABAR_GYM", "BLAINE"): "EVENT_BEAT_BLAINE",
    ("VIRIDIAN_GYM", "GIOVANNI"): "EVENT_BEAT_VIRIDIAN_GYM_GIOVANNI",
    ("LORELEIS_ROOM", "LORELEI"): "EVENT_BEAT_LORELEIS_ROOM_TRAINER_0",
    ("BRUNOS_ROOM", "BRUNO"): "EVENT_BEAT_BRUNOS_ROOM_TRAINER_0",
    ("AGATHAS_ROOM", "AGATHA"): "EVENT_BEAT_AGATHAS_ROOM_TRAINER_0",
    ("LANCES_ROOM", "LANCE"): "EVENT_BEAT_LANCES_ROOM_TRAINER_0",
    ("ROCKET_HIDEOUT_B4F", "GIOVANNI"): "EVENT_BEAT_ROCKET_HIDEOUT_GIOVANNI",
    ("ROUTE_24", "ROCKET"): "EVENT_BEAT_ROUTE24_ROCKET",
    ("SILPH_CO_11F", "GIOVANNI"): "EVENT_BEAT_SILPH_CO_GIOVANNI",
    ("VICTORY_ROAD_2F", "MOLTRES"): "EVENT_BEAT_MOLTRES",
    ("CERULEAN_CITY", "RIVAL1"): "EVENT_BEAT_CERULEAN_RIVAL",
    ("OAKS_LAB", "RIVAL1"): "EVENT_BATTLED_RIVAL_IN_OAKS_LAB",
}

SPECIAL_OBJECT_EVENTS = {
    ("FIGHTING_DOJO", 0): "EVENT_BEAT_KARATE_MASTER",
    ("MT_MOON_B2F", 0): "EVENT_BEAT_MT_MOON_EXIT_SUPER_NERD",
    ("ROUTE_24", 0): "EVENT_BEAT_ROUTE24_ROCKET",
    ("CERULEAN_CITY", 1): "EVENT_BEAT_CERULEAN_ROCKET_THIEF",
    ("GAME_CORNER", 10): "EVENT_FOUND_ROCKET_HIDEOUT",
}


def _event_constants(root: Path) -> dict[str, int]:
    """Evaluate the const-only event table without requiring an RGBDS build."""
    result: dict[str, int] = {}
    value = 0
    for raw in (root / "constants/event_constants.asm").read_text(encoding="utf-8").splitlines():
        line = raw.split(";", 1)[0].strip()
        match = re.fullmatch(r"const_def(?:\s+\$([0-9A-Fa-f]+))?", line)
        if match:
            value = int(match.group(1), 16) if match.group(1) else 0
            continue
        match = re.fullmatch(r"const_next\s+\$([0-9A-Fa-f]+)(?:\s*-\s*(\d+))?", line)
        if match:
            value = int(match.group(1), 16) - int(match.group(2) or 0)
            continue
        match = re.fullmatch(r"const_skip(?:\s+(\d+))?", line)
        if match:
            value += int(match.group(1) or 1)
            continue
        match = re.fullmatch(r"const\s+(EVENT_[A-Z0-9_]+)", line)
        if match:
            result[match.group(1)] = value
            value += 1
    if value != 0xA00:
        raise ValueError(f"expected 0xA00 event bits, got {value:#x}")
    return result


def _toggleable_object_indexes(root: Path) -> dict[tuple[str, int], int]:
    exports: dict[str, dict[str, int]] = {}
    for path in (root / "data/maps/objects").glob("*.asm"):
        text = path.read_text(encoding="utf-8")
        map_symbol = _map_symbol_for_object(text)
        if not map_symbol:
            continue
        names = re.findall(r"^\s*const_export\s+([A-Z0-9_]+)", text, re.M)
        exports[map_symbol] = {name: index for index, name in enumerate(names, 1)}
    result: dict[tuple[str, int], int] = {}
    current_map = None
    index = 0
    text = (root / "data/maps/toggleable_objects.asm").read_text(encoding="utf-8")
    for line in text.splitlines():
        header = re.match(r"\s*toggleable_objects_for\s+([A-Z0-9_]+)", line)
        if header:
            current_map = header.group(1)
            continue
        entry = re.match(r"\s*toggle_object_state\s+([A-Z0-9_$]+),", line)
        if entry and current_map:
            symbol = entry.group(1)
            if not symbol.startswith("$"):
                result[(current_map, exports[current_map][symbol])] = index
            index += 1
    if index != 0xE4:
        raise ValueError(f"expected 228 toggleable object records, got {index}")
    return result


def _active_lines(text: str, version: str) -> list[str]:
    active = True
    stack: list[tuple[bool, bool]] = []
    result = []
    for raw in text.splitlines():
        stripped = raw.strip()
        match = re.match(r"IF DEF\(_(RED|BLUE)\)", stripped)
        if match:
            condition = match.group(1).lower() == version
            stack.append((active, condition))
            active = active and condition
        elif stripped == "ELSE":
            parent, condition = stack[-1]
            stack[-1] = (parent, not condition)
            active = parent and not condition
        elif stripped == "ENDC":
            parent, _ = stack.pop()
            active = parent
        elif active:
            result.append(raw.split(";", 1)[0].rstrip())
    if stack:
        raise ValueError("unterminated version conditional")
    return result


def _display(symbol: str) -> str:
    special = {
        "POKE_BALL": "Poké Ball", "PP_UP": "PP Up", "MAX_PP": "Max PP",
        "TM": "TM", "HM": "HM", "JR_TRAINER_M": "Jr. Trainer♂",
        "JR_TRAINER_F": "Jr. Trainer♀", "COOLTRAINER_M": "Cooltrainer♂",
        "COOLTRAINER_F": "Cooltrainer♀", "NIDORAN_M": "Nidoran♂",
        "NIDORAN_F": "Nidoran♀", "FARFETCHD": "Farfetch'd", "MR_MIME": "Mr. Mime",
    }
    if symbol.startswith(("TM_", "HM_")):
        prefix, name = symbol.split("_", 1)
        return f"{prefix} {name.replace('_', ' ').title()}"
    return special.get(symbol, symbol.replace("_", " ").title())


def _stable(symbol: str) -> str:
    return symbol.lower()


def _map_constants(root: Path) -> tuple[dict[str, int], dict[int, str]]:
    symbols: dict[str, int] = {}
    stable: dict[int, str] = {}
    value = 0
    for line in (root / "constants/map_constants.asm").read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*map_const\s+([A-Z0-9_]+),", line)
        if match:
            symbol = match.group(1)
            symbols[symbol] = value
            stable[value] = _stable(symbol)
            value += 1
    if value != 248:
        raise ValueError(f"expected 248 maps, got {value}")
    return symbols, stable


def _species_constants(root: Path) -> dict[str, int]:
    result = {}
    for line in (root / "constants/pokemon_constants.asm").read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*const\s+([A-Z0-9_]+)\s*;\s*\$([0-9A-Fa-f]+)", line)
        if match:
            result[match.group(1)] = int(match.group(2), 16)
    return result


def _wild_tables(root: Path, version: str) -> dict[str, dict[str, object]]:
    tables: dict[str, dict[str, object]] = {}
    for path in sorted((root / "data/wild/maps").glob("*.asm")):
        current = None
        method = None
        for line in _active_lines(path.read_text(encoding="utf-8"), version):
            label = re.match(r"^([A-Za-z0-9]+)WildMons:$", line)
            if label:
                current = label.group(1) + "WildMons"
                tables[current] = {"_source_path": path.relative_to(root).as_posix()}
                method = None
                continue
            start = re.match(r"\s*def_(grass|water)_wildmons\s+(\d+)", line)
            if current and start:
                method = start.group(1)
                tables[current][method] = {"encounter_rate": int(start.group(2)), "slots": []}
                continue
            entry = re.match(r"\s*db\s+(\d+),\s*([A-Z0-9_]+)", line)
            if current and method and entry:
                tables[current][method]["slots"].append((int(entry.group(1)), entry.group(2)))
    return tables


def _encounters(root: Path, version: str, maps: dict[str, int], species: dict[str, int]) -> list[dict[str, object]]:
    tables = _wild_tables(root, version)
    pointer_lines = []
    in_table = False
    for line in (root / "data/wild/grass_water.asm").read_text(encoding="utf-8").splitlines():
        if line.startswith("WildDataPointers:"):
            in_table = True
            continue
        if in_table and line.lstrip().startswith("INCLUDE"):
            break
        if in_table:
            match = re.match(r"\s*dw\s+([A-Za-z0-9]+WildMons)", line)
            if match:
                pointer_lines.append(match.group(1))
    if len(pointer_lines) != 248:
        raise ValueError(f"expected 248 wild pointers, got {len(pointer_lines)}")
    by_id = {value: symbol for symbol, value in maps.items()}
    records = []
    for map_id, table_name in enumerate(pointer_lines):
        table = tables.get(table_name)
        if not table:
            continue
        for method, method_data in table.items():
            if method.startswith("_"):
                continue
            slots = method_data["slots"]
            if method_data["encounter_rate"] == 0:
                continue
            if len(slots) != 10:
                raise ValueError(f"{table_name} {method} has {len(slots)} slots")
            for slot, ((level, species_symbol), weight) in enumerate(zip(slots, SLOT_WEIGHTS)):
                records.append({
                    "version": version,
                    "map_id": map_id,
                    "map_symbol": by_id[map_id],
                    "area_id": _stable(by_id[map_id]),
                    "method": "grass" if method == "grass" else "surf",
                    "slot": slot,
                    "species_id": species[species_symbol],
                    "level": level,
                    "weight": weight,
                    "weight_denominator": 256,
                    "encounter_rate": method_data["encounter_rate"],
                    "source_ref": f"{table['_source_path']}:{table_name}:{method}:slot_{slot}",
                })
    return records


def _super_rod_encounters(root: Path, version: str, maps: dict[str, int], species: dict[str, int]) -> list[dict[str, object]]:
    text = (root / "data/wild/super_rod.asm").read_text(encoding="utf-8")
    assignments = re.findall(r"^\s*dbw\s+([A-Z0-9_]+),\s*\.Group(\d+)", text, re.M)
    groups: dict[str, list[tuple[int, str]]] = {}
    current = None
    expected = None
    for line in text.splitlines():
        label = re.match(r"^\.Group(\d+):", line)
        if label:
            current = label.group(1)
            groups[current] = []
            expected = None
            continue
        count = re.match(r"\s*db\s+(\d+)\s*$", line)
        if current and count and expected is None:
            expected = int(count.group(1))
            continue
        entry = re.match(r"\s*db\s+(\d+),\s*([A-Z0-9_]+)", line)
        if current and expected is not None and entry:
            groups[current].append((int(entry.group(1)), entry.group(2)))
    for group, entries in groups.items():
        if not entries or len(entries) > 4:
            raise ValueError(f"invalid Super Rod group {group}")
    records = []
    for map_symbol, group in assignments:
        entries = groups[group]
        for slot, (level, species_symbol) in enumerate(entries):
            records.append({
                "version": version, "map_id": maps[map_symbol], "map_symbol": map_symbol,
                "area_id": _stable(map_symbol), "method": "super_rod", "slot": slot,
                "species_id": species[species_symbol], "level": level,
                "weight": 1, "weight_denominator": len(entries),
                "encounter_rate": 128,
                "requires_fishable_tile": True,
                "source_ref": f"data/wild/super_rod.asm:Group{group}:slot_{slot}",
            })
    return records


def _trainer_parties(root: Path, species: dict[str, int]) -> dict[str, list[list[dict[str, int]]]]:
    constants = []
    for line in (root / "constants/trainer_constants.asm").read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*trainer_const\s+([A-Z0-9_]+)", line)
        if match and match.group(1) != "NOBODY":
            constants.append(match.group(1))
    text = (root / "data/trainers/parties.asm").read_text(encoding="utf-8")
    labels = re.findall(r"^\s*dw\s+([A-Za-z0-9]+Data)\s*$", text, re.M)[:len(constants)]
    if len(labels) != len(constants):
        raise ValueError("trainer class pointer mismatch")
    label_to_class = dict(zip(labels, constants))
    result = {token: [] for token in constants}
    current = None
    for line in text.splitlines():
        label = re.match(r"^([A-Za-z0-9]+Data):$", line)
        if label:
            current = label_to_class.get(label.group(1))
            continue
        match = re.match(r"\s*db\s+(.+?)(?:\s*;.*)?$", line)
        if not current or not match:
            continue
        values = [part.strip() for part in match.group(1).split(",")]
        if not values or values[-1] != "0":
            continue
        values = values[:-1]
        team = []
        if values[0].upper() == "$FF":
            values = values[1:]
            if len(values) % 2:
                raise ValueError(f"invalid variable-level party: {line}")
            for level, mon in zip(values[::2], values[1::2]):
                team.append({"species_id": species[mon], "level": int(level)})
        else:
            level = int(values[0])
            team = [{"species_id": species[mon], "level": level} for mon in values[1:]]
        result[current].append(team)
    return result


def _map_symbol_for_object(text: str) -> str | None:
    match = re.search(r"^\s*def_warps_to\s+([A-Z0-9_]+)", text, re.M)
    return match.group(1) if match else None


def _objects(
    root: Path,
    version: str,
    maps: dict[str, int],
    parties: dict[str, list[list[dict[str, int]]]],
    event_constants: dict[str, int],
    toggle_indexes: dict[tuple[str, int], int],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    trainers = []
    items = []
    for path in sorted((root / "data/maps/objects").glob("*.asm")):
        text = "\n".join(_active_lines(path.read_text(encoding="utf-8"), version))
        map_symbol = _map_symbol_for_object(text)
        if map_symbol not in maps:
            continue
        map_trainers = []
        object_index = 0
        for line in text.splitlines():
            match = re.match(r"\s*object_event\s+(.+)$", line)
            if not match:
                continue
            args = [part.strip() for part in match.group(1).split(",")]
            x, y = int(args[0]), int(args[1])
            if len(args) >= 8 and args[6].startswith("OPP_"):
                trainer_class = args[6].removeprefix("OPP_")
                party_index = int(args[7])
                class_parties = parties.get(trainer_class)
                if class_parties is None or not 1 <= party_index <= len(class_parties):
                    raise ValueError(f"unknown trainer party in {path}: {line}")
                map_trainers.append({
                    "trainer_id": f"{_stable(map_symbol)}:{object_index}:{_stable(trainer_class)}:{party_index}",
                    "version": version,
                    "map_id": maps[map_symbol],
                    "area_id": _stable(map_symbol),
                    "object_index": object_index,
                    "x": x, "y": y,
                    "trainer_class_id": _stable(trainer_class),
                    "trainer_class_name": _display(trainer_class),
                    "party_index": party_index,
                    "party": class_parties[party_index - 1],
                    "party_selection": "script_dependent" if trainer_class.startswith("RIVAL") else "object_party_index",
                    "source_ref": f"{path.relative_to(root).as_posix()}:object_{object_index};data/trainers/parties.asm:{trainer_class}:party_{party_index}",
                })
            elif len(args) == 7 and args[2] == "SPRITE_POKE_BALL":
                item_symbol = args[6]
                items.append({
                    "placement_id": f"{_stable(map_symbol)}:{x}:{y}:{_stable(item_symbol)}:visible",
                    "version": version,
                    "map_id": maps[map_symbol],
                    "area_id": _stable(map_symbol),
                    "x": x, "y": y,
                    "item_id": _stable(item_symbol),
                    "item_name": _display(item_symbol),
                    "hidden": False,
                    "toggleable_object_flag_index": toggle_indexes.get((map_symbol, object_index + 1)),
                    "accessible": True,
                    "source_ref": f"{path.relative_to(root).as_posix()}:object_{object_index}",
                })
            object_index += 1
        script_path = root / "scripts" / path.name
        trainer_events = []
        if script_path.exists():
            script_text = script_path.read_text(encoding="utf-8")
            trainer_events = re.findall(r"^\s*trainer\s+(EVENT_[A-Z0-9_]+)", script_text, re.M)
            if len(trainer_events) != len(map_trainers):
                trainer_events = sorted(
                    set(re.findall(r"EVENT_BEAT_[A-Z0-9_]*TRAINER_\d+", script_text)),
                    key=lambda event: int(event.rsplit("_", 1)[1]),
                )

        unresolved = []
        assigned_symbols = set()
        for trainer in map_trainers:
            event_symbol = SPECIAL_OBJECT_EVENTS.get((map_symbol, trainer["object_index"]))
            event_symbol = event_symbol or BOSS_EVENTS.get((map_symbol, trainer["trainer_class_id"].upper()))
            if event_symbol:
                trainer["event_symbol"] = event_symbol
                trainer["event_flag_index"] = event_constants[event_symbol]
                assigned_symbols.add(event_symbol)
            else:
                unresolved.append(trainer)
        trainer_events = [event for event in trainer_events if event not in assigned_symbols]
        if len(unresolved) == len(trainer_events):
            for trainer, event_symbol in zip(unresolved, trainer_events):
                trainer["event_symbol"] = event_symbol
                trainer["event_flag_index"] = event_constants[event_symbol]
        trainers.extend(map_trainers)
    return trainers, items


def _hidden_items(root: Path, maps: dict[str, int]) -> list[dict[str, object]]:
    coords = []
    for line in (root / "data/events/hidden_item_coords.asm").read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*hidden_item\s+([A-Z0-9_]+),\s*(\d+),\s*(\d+)(?:\s*;\s*(.*))?", line)
        if match:
            coords.append((match.group(1), int(match.group(2)), int(match.group(3)), match.group(4) or ""))
    events: dict[tuple[str, int, int], tuple[str, str]] = {}
    current_map = None
    for line in (root / "data/events/hidden_events.asm").read_text(encoding="utf-8").splitlines():
        header = re.match(r"\s*hidden_events_for\s+([A-Z0-9_]+)", line)
        if header:
            current_map = header.group(1)
            continue
        match = re.match(r"\s*hidden_event\s+(\d+),\s*(\d+),\s*HiddenItems,\s*([A-Z0-9_]+)(?:\s*;\s*(.*))?", line)
        if match and current_map:
            events[(current_map, int(match.group(1)), int(match.group(2)))] = (match.group(3), match.group(4) or "")
    if len(coords) != len(events):
        raise ValueError(f"hidden item table mismatch: {len(coords)} coords, {len(events)} events")
    result = []
    for index, (map_symbol, x, y, coord_note) in enumerate(coords):
        try:
            item_symbol, event_note = events[(map_symbol, x, y)]
        except KeyError as exc:
            raise ValueError(f"hidden item event missing for {map_symbol} ({x}, {y})") from exc
        note = coord_note or event_note
        result.append({
            "placement_id": f"{_stable(map_symbol)}:{x}:{y}:{_stable(item_symbol)}:hidden",
            "version": "both",
            "map_id": maps[map_symbol],
            "area_id": _stable(map_symbol),
            "x": x, "y": y,
            "item_id": _stable(item_symbol),
            "item_name": _display(item_symbol),
            "hidden": True,
            "accessible": "inaccessible" not in note.lower(),
            "note": note or None,
            "hidden_item_flag_index": index,
            "source_ref": f"data/events/hidden_item_coords.asm:index_{index};data/events/hidden_events.asm:{map_symbol}:{x}:{y}",
        })
    return result


def _connections(root: Path, maps: dict[str, int]) -> list[dict[str, object]]:
    result = []
    for path in sorted((root / "data/maps/headers").glob("*.asm")):
        text = path.read_text(encoding="utf-8")
        header = re.search(r"\s*map_header\s+[^,]+,\s*([A-Z0-9_]+),", text)
        if not header or header.group(1) not in maps:
            continue
        source = header.group(1)
        for direction, target in re.findall(r"\s*connection\s+(north|south|east|west),\s*[^,]+,\s*([A-Z0-9_]+),", text):
            result.append({
                "from_map_id": maps[source],
                "to_map_id": maps[target],
                "direction": direction,
                "source_ref": path.relative_to(root).as_posix(),
            })
    return result


def _source_hash(root: Path, paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big")); digest.update(relative)
        digest.update(len(data).to_bytes(8, "big")); digest.update(data)
    return digest.hexdigest()


def generate(root: Path, commit: str) -> dict[str, object]:
    maps, _ = _map_constants(root)
    species = _species_constants(root)
    event_constants = _event_constants(root)
    toggle_indexes = _toggleable_object_indexes(root)
    parties = _trainer_parties(root, species)
    encounters = []
    trainers = []
    visible_items = []
    for version in ("red", "blue"):
        encounters.extend(_encounters(root, version, maps, species))
        encounters.extend(_super_rod_encounters(root, version, maps, species))
        version_trainers, version_items = _objects(
            root, version, maps, parties, event_constants, toggle_indexes
        )
        for party_index, rival_starter in enumerate(("SQUIRTLE", "BULBASAUR", "CHARMANDER"), 1):
            version_trainers.append({
                "trainer_id": f"champions_room:0:rival3:{party_index}",
                "version": version,
                "map_id": maps["CHAMPIONS_ROOM"],
                "area_id": "champions_room",
                "object_index": 0,
                "x": 4,
                "y": 2,
                "trainer_class_id": "rival3",
                "trainer_class_name": "Champion Rival",
                "party_index": party_index,
                "party": parties["RIVAL3"][party_index - 1],
                "party_selection": "rival_starter",
                "rival_starter_id": species[rival_starter],
                "event_symbol": "EVENT_BEAT_CHAMPION_RIVAL",
                "event_flag_index": event_constants["EVENT_BEAT_CHAMPION_RIVAL"],
                "source_ref": "scripts/ChampionsRoom.asm;data/trainers/parties.asm:RIVAL3",
            })
        trainers.extend(version_trainers)
        visible_items.extend(version_items)
    sources = [
        root / "constants/map_constants.asm", root / "constants/pokemon_constants.asm",
        root / "constants/trainer_constants.asm", root / "data/trainers/parties.asm",
        root / "data/wild/grass_water.asm", root / "data/wild/probabilities.asm",
        root / "data/wild/super_rod.asm",
        root / "data/events/hidden_item_coords.asm", root / "data/events/hidden_events.asm",
        root / "constants/event_constants.asm", root / "constants/toggle_constants.asm",
        root / "data/maps/toggleable_objects.asm",
        *sorted((root / "scripts").glob("*.asm")),
        *sorted((root / "data/wild/maps").glob("*.asm")),
        *sorted((root / "data/maps/headers").glob("*.asm")),
        *sorted((root / "data/maps/objects").glob("*.asm")),
    ]
    return {
        "schema_version": 2,
        "source": "pret/pokered",
        "source_commit": commit,
        "source_sha256": _source_hash(root, sources),
        "encounters": encounters,
        "trainers": trainers,
        "items": visible_items + _hidden_items(root, maps),
        "connections": _connections(root, maps),
        "event_constants": event_constants,
        "limitations": [
            "Grass, Surf, and exact map-specific Super Rod tables are included; Old/Good Rod availability still requires fishable-tile topology.",
            "Most persistent trainer defeat flags are attached; a few scripted rival and special battles do not retain an independent defeat bit.",
            "Script-dependent rival party selection is flagged and excluded from automatic next-trainer selection.",
            "Coordinates are exact map tile coordinates, not prose walkthrough directions.",
            "Visible object items and hidden items are included with persistent collection flags; shops, gifts, and battle rewards are not yet included.",
        ],
    }


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: import_pokered_world_data.py POKERED_ROOT OUTPUT_JSON COMMIT_SHA")
    root, output, commit = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    payload = generate(root, commit)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
