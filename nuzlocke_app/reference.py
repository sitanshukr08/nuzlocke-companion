"""Read-only canonical Gen I world data and location-aware queries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from gen1_save_parser.layout.gen1_battle_data import get_move, get_species_base_data, get_type
from gen1_save_parser.layout.gen1_maps import get_map
from gen1_save_parser.mechanics import calculate_party_stats
from gen1_save_parser.models import GameVersion


DATA_PATH = Path(__file__).parent / "data" / "gen1_world.json"

CERULEAN_RIVAL_PARTIES = {
    0xB1: ((0x96, 18), (0x94, 15), (0xA5, 15), (0xB1, 17)),  # Squirtle
    0x99: ((0x96, 18), (0x94, 15), (0xA5, 15), (0x99, 17)),  # Bulbasaur
    0xB0: ((0x96, 18), (0x94, 15), (0xA5, 15), (0xB0, 17)),  # Charmander
}

TRAINER_AVAILABILITY_EVENTS = {
    "cerulean_city:1:rocket:5": "EVENT_GOT_SS_TICKET",
}
GYM_SPECIAL_MOVES = {
    "brock": (1, 0x75), "misty": (1, 0x3D), "lt_surge": (2, 0x55),
    "erika": (2, 0x48), "koga": (3, 0x5C), "sabrina": (3, 0x95),
    "blaine": (3, 0x7E),
}
ELITE_SPECIAL_MOVES = {
    "lorelei": (4, 0x3B), "bruno": (4, 0x5A),
    "agatha": (4, 0x5C), "lance": (4, 0x70),
}
SPECIAL_MOVE_TYPE_IDS = frozenset({0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A})


@dataclass(frozen=True)
class EncounterSummary:
    area_id: str
    map_id: int
    method: str
    species_id: int
    species_name: str
    type_names: tuple[str, ...]
    levels: tuple[int, ...]
    slot_weight: int
    slot_weight_denominator: int
    encounter_rate: int


@dataclass(frozen=True)
class TrainerSummary:
    trainer_id: str
    area_id: str
    map_id: int
    map_name: str
    x: int
    y: int
    trainer_class: str
    party: tuple[dict[str, object], ...]
    selection_basis: str
    defeated: bool | None = None
    event_symbol: str | None = None


@dataclass(frozen=True)
class EncounterChoice:
    area_id: str
    map_id: int
    map_name: str
    method: str
    species_id: int
    species_name: str
    type_names: tuple[str, ...]
    valid_levels: tuple[int, ...]


@dataclass(frozen=True)
class EncounterAreaChoice:
    area_id: str
    map_id: int
    map_name: str
    methods: tuple[str, ...]


class Gen1WorldDatabase:
    def __init__(self, path: str | Path = DATA_PATH):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        battle_path = Path(__file__).parent / "data" / "gen1_trainer_battle.json"
        self.trainer_battle_data = json.loads(battle_path.read_text(encoding="utf-8"))
        if self.data.get("schema_version") != 2:
            raise ValueError("unsupported Gen I world-data schema")

    @property
    def source_provenance(self) -> dict[str, str]:
        return {
            "source": self.data["source"],
            "commit": self.data["source_commit"],
            "sha256": self.data["source_sha256"],
        }

    @cached_property
    def _connections(self) -> dict[int, list[dict[str, object]]]:
        result: dict[int, list[dict[str, object]]] = {}
        for connection in self.data["connections"]:
            result.setdefault(connection["from_map_id"], []).append(connection)
        return result

    def connected_maps(self, map_id: int) -> tuple[dict[str, object], ...]:
        return tuple(self._connections.get(map_id, ()))

    def encounter_summaries(self, map_id: int, version: GameVersion) -> tuple[EncounterSummary, ...]:
        grouped: dict[tuple[str, int], dict[str, object]] = {}
        for entry in self.data["encounters"]:
            if entry["map_id"] != map_id or entry["version"] != version.value:
                continue
            key = (entry["method"], entry["species_id"])
            group = grouped.setdefault(key, {
                "entry": entry, "levels": set(), "weight": 0,
            })
            group["levels"].add(entry["level"])
            group["weight"] += entry["weight"]
        summaries = []
        for group in grouped.values():
            entry = group["entry"]
            species = get_species_base_data(entry["species_id"])
            type_ids = dict.fromkeys((species.type1_id, species.type2_id))
            summaries.append(EncounterSummary(
                area_id=entry["area_id"], map_id=map_id, method=entry["method"],
                species_id=species.internal_id, species_name=species.display_name,
                type_names=tuple(get_type(type_id).display_name for type_id in type_ids),
                levels=tuple(sorted(group["levels"])), slot_weight=group["weight"],
                slot_weight_denominator=entry["weight_denominator"],
                encounter_rate=entry["encounter_rate"],
            ))
        return tuple(sorted(summaries, key=lambda item: (item.method, -item.slot_weight, item.species_name)))

    def items_for_map(
        self, map_id: int, version: GameVersion, *, state: object | None = None
    ) -> tuple[dict[str, object], ...]:
        items = tuple(
            dict(item) for item in self.data["items"]
            if item["map_id"] == map_id and item["version"] in (version.value, "both")
        )
        if state is None:
            return items
        hidden_flags = getattr(state, "obtained_hidden_item_flags", frozenset())
        toggle_flags = getattr(state, "toggleable_object_flags", frozenset())
        for item in items:
            flag = (
                item.get("hidden_item_flag_index") if item["hidden"]
                else item.get("toggleable_object_flag_index")
            )
            item["collected"] = None if flag is None else flag in (
                hidden_flags if item["hidden"] else toggle_flags
            )
        return items

    def encounter_choices(self, area_id: str, version: GameVersion) -> tuple[EncounterChoice, ...]:
        records = [
            entry for entry in self.data["encounters"]
            if entry["area_id"] == area_id and entry["version"] == version.value
        ]
        grouped: dict[tuple[str, int], set[int]] = {}
        for entry in records:
            grouped.setdefault((entry["method"], entry["species_id"]), set()).add(entry["level"])
        choices = []
        for (method, species_id), levels in grouped.items():
            species = get_species_base_data(species_id)
            type_ids = dict.fromkeys((species.type1_id, species.type2_id))
            map_id = records[0]["map_id"]
            choices.append(EncounterChoice(
                area_id=area_id, map_id=map_id, map_name=get_map(map_id).display_name,
                method=method, species_id=species_id, species_name=species.display_name,
                type_names=tuple(get_type(type_id).display_name for type_id in type_ids),
                valid_levels=tuple(sorted(levels)),
            ))
        return tuple(sorted(choices, key=lambda item: (item.method, item.species_name)))

    def encounter_areas(self, version: GameVersion) -> tuple[EncounterAreaChoice, ...]:
        grouped: dict[str, dict[str, object]] = {}
        for entry in self.data["encounters"]:
            if entry["version"] != version.value:
                continue
            group = grouped.setdefault(entry["area_id"], {"map_id": entry["map_id"], "methods": set()})
            group["methods"].add(entry["method"])
        return tuple(sorted((
            EncounterAreaChoice(
                area_id=area_id, map_id=value["map_id"],
                map_name=get_map(value["map_id"]).display_name,
                methods=tuple(sorted(value["methods"])),
            )
            for area_id, value in grouped.items()
        ), key=lambda area: area.map_id))

    def trainers_for_map(self, map_id: int, version: GameVersion) -> tuple[dict[str, object], ...]:
        # Identical teams are stored per version so future version differences remain representable.
        return tuple(
            trainer for trainer in self.data["trainers"]
            if trainer["map_id"] == map_id and trainer["version"] == version.value
        )

    def scripted_trainers_for_map(
        self, map_id: int, version: GameVersion, state: object
    ) -> tuple[dict[str, object], ...]:
        del version  # The Cerulean rival teams are identical in Red and Blue.
        if map_id != 0x03:
            return ()
        rival_starter = getattr(state, "rival_starter_id", None)
        party = CERULEAN_RIVAL_PARTIES.get(rival_starter)
        if party is None:
            return ()
        event_symbol = "EVENT_BEAT_CERULEAN_RIVAL"
        return ({
            "trainer_id": "cerulean_city:script:rival1:cerulean",
            "area_id": "cerulean_city",
            "map_id": 0x03,
            "x": 20,
            "y": 2,
            "trainer_class_name": "Rival",
            "party": [{"species_id": species_id, "level": level} for species_id, level in party],
            "event_symbol": event_symbol,
            "event_flag_index": self.data["event_constants"][event_symbol],
            "source_ref": "scripts/CeruleanCity.asm;data/trainers/parties.asm:RIVAL1:parties_7_to_9",
        },)

    def trainer_is_available(self, trainer: dict[str, object], state: object | None) -> bool:
        if state is None:
            return True
        required_event = TRAINER_AVAILABILITY_EVENTS.get(str(trainer["trainer_id"]))
        return required_event is None or self.event_is_set(state, required_event)

    def event_is_set(self, state: object, event_symbol: str) -> bool:
        return self.data["event_constants"][event_symbol] in getattr(state, "event_flags", ())

    def trainer_is_defeated(self, trainer: dict[str, object], state: object) -> bool | None:
        flag = trainer.get("event_flag_index")
        return None if flag is None else flag in getattr(state, "event_flags", ())

    def defeated_trainer_ids(self, state: object, version: GameVersion) -> frozenset[str]:
        return frozenset(
            trainer["trainer_id"] for trainer in self.data["trainers"]
            if trainer["version"] == version.value and self.trainer_is_defeated(trainer, state) is True
        )

    def _party_details(
        self, party: list[dict[str, int]], trainer: dict[str, object]
    ) -> tuple[dict[str, object], ...]:
        result = []
        for member_index, member in enumerate(party):
            species = get_species_base_data(member["species_id"])
            type_ids = dict.fromkeys((species.type1_id, species.type2_id))
            learnset = self.trainer_battle_data["species"][str(member["species_id"])]
            move_slots = list(learnset["starting_moves"][:4])
            move_slots.extend([0] * (4 - len(move_slots)))
            for learned_level, move_id in learnset["level_up_moves"]:
                if learned_level > member["level"]:
                    break
                if move_id in move_slots:
                    continue
                try:
                    move_slots[move_slots.index(0)] = move_id
                except ValueError:
                    move_slots = move_slots[1:] + [move_id]

            trainer_class_id = str(trainer.get("trainer_class_id", ""))
            override = GYM_SPECIAL_MOVES.get(trainer_class_id) or ELITE_SPECIAL_MOVES.get(trainer_class_id)
            if trainer_class_id == "giovanni" and trainer.get("area_id") == "viridian_gym":
                override = (4, 0x5A)
            if override and member_index == override[0]:
                move_slots[2] = override[1]
            if trainer_class_id == "rival3":
                if member_index == 0:
                    move_slots[2] = 0x8F
                elif member_index == 5:
                    move_slots[2] = {0x9A: 0x48, 0xB4: 0x7E, 0x1C: 0x3B}.get(
                        member["species_id"], move_slots[2]
                    )

            moves = []
            for move_id in move_slots:
                if not move_id:
                    continue
                move = get_move(move_id)
                move_type = get_type(move.type_id)
                moves.append({
                    "move_id": move.move_id, "move_name": move.display_name,
                    "type": move_type.display_name, "power": move.power,
                    "accuracy": move.accuracy_percent, "pp": move.base_pp,
                    "category": "Status" if move.power == 0 else (
                        "Special" if move.type_id in SPECIAL_MOVE_TYPE_IDS else "Physical"
                    ),
                    "effect": move.effect_id,
                })
            stats = calculate_party_stats(species, 0x9888, [0, 0, 0, 0, 0], member["level"])
            result.append({
                "species_id": species.internal_id,
                "species_name": species.display_name,
                "level": member["level"],
                "types": [get_type(type_id).display_name for type_id in type_ids],
                "stats": stats, "moves": moves,
                "trainer_dvs": {"hp": 8, "attack": 9, "defense": 8, "speed": 8, "special": 8},
                "stat_exp": 0,
                "battle_data_basis": "exact_red_blue_trainer_generation",
            })
        return tuple(result)

    def trainer_summary(
        self, trainer: dict[str, object], *, basis: str, state: object | None = None
    ) -> TrainerSummary:
        map_definition = get_map(trainer["map_id"])
        return TrainerSummary(
            trainer_id=trainer["trainer_id"], area_id=trainer["area_id"],
            map_id=trainer["map_id"], map_name=map_definition.display_name,
            x=trainer["x"], y=trainer["y"], trainer_class=trainer["trainer_class_name"],
            party=self._party_details(trainer["party"], trainer), selection_basis=basis,
            defeated=self.trainer_is_defeated(trainer, state) if state is not None else None,
            event_symbol=trainer.get("event_symbol"),
        )

    def next_trainer_candidate(
        self,
        *,
        map_id: int,
        version: GameVersion,
        player_x: int | None,
        player_y: int | None,
        defeated_trainer_ids: frozenset[str] = frozenset(),
        allowed_connected_map_ids: frozenset[int] | None = None,
        state: object | None = None,
    ) -> TrainerSummary | None:
        candidates = self.reachable_trainer_candidates(
            map_id=map_id, version=version, player_x=player_x, player_y=player_y,
            defeated_trainer_ids=defeated_trainer_ids,
            allowed_connected_map_ids=allowed_connected_map_ids, state=state,
        )
        return candidates[0] if candidates else None

    def reachable_trainer_candidates(
        self,
        *,
        map_id: int,
        version: GameVersion,
        player_x: int | None,
        player_y: int | None,
        defeated_trainer_ids: frozenset[str] = frozenset(),
        allowed_connected_map_ids: frozenset[int] | None = None,
        state: object | None = None,
    ) -> tuple[TrainerSummary, ...]:
        """Return every eligible local/adjacent trainer, nearest first."""
        def eligible(trainer: dict[str, object]) -> bool:
            return (
                trainer["trainer_id"] not in defeated_trainer_ids
                and self.trainer_is_available(trainer, state)
                and trainer.get("party_selection") != "script_dependent"
                and (
                    trainer.get("party_selection") != "rival_starter"
                    or trainer.get("rival_starter_id") == getattr(state, "rival_starter_id", None)
                )
            )

        local_trainers = self.trainers_for_map(map_id, version) + self.scripted_trainers_for_map(
            map_id, version, state
        )
        candidates = [
            (trainer, "same_map_manhattan_distance", abs(trainer["x"] - (player_x or 0)) + abs(trainer["y"] - (player_y or 0)))
            for trainer in local_trainers
            if eligible(trainer)
        ]
        for connection in self.connected_maps(map_id):
            target_id = connection["to_map_id"]
            if allowed_connected_map_ids is not None and target_id not in allowed_connected_map_ids:
                continue
            target = get_map(target_id)
            connected_trainers = self.trainers_for_map(
                target_id, version
            ) + self.scripted_trainers_for_map(target_id, version, state)
            for trainer in connected_trainers:
                if not eligible(trainer):
                    continue
                direction = connection["direction"]
                if direction == "east":
                    distance = trainer["x"] + abs(trainer["y"] - target.height_blocks)
                elif direction == "west":
                    distance = target.width_blocks * 2 - 1 - trainer["x"] + abs(trainer["y"] - target.height_blocks)
                elif direction == "south":
                    distance = trainer["y"] + abs(trainer["x"] - target.width_blocks)
                else:
                    distance = target.height_blocks * 2 - 1 - trainer["y"] + abs(trainer["x"] - target.width_blocks)
                candidates.append((trainer, "connected_map_entry_coordinate_heuristic", distance))
        candidates.sort(key=lambda value: (
            0 if value[1] == "same_map_manhattan_distance" else 1,
            value[2], value[0]["trainer_id"],
        ))
        return tuple(
            self.trainer_summary(trainer, basis=basis, state=state)
            for trainer, basis, _ in candidates
        )
