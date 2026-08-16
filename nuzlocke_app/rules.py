"""Deterministic Nuzlocke history and location-guidance rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum

from gen1_save_parser.layout.gen1_maps import get_map
from gen1_save_parser.models import GameVersion, SaveState

from .reference import Gen1WorldDatabase, TrainerSummary


class EncounterStatus(str, Enum):
    UNCLAIMED = "unclaimed"
    ENCOUNTERED = "encountered"
    CAUGHT = "caught"
    MISSED = "missed"
    FLED = "fled"
    FAINTED = "fainted"


class EncounterSource(str, Enum):
    WILD = "wild"
    GIFT = "gift"
    STATIC = "static"
    TRADE = "trade"


CONSUMING_STATUSES = frozenset({
    EncounterStatus.ENCOUNTERED, EncounterStatus.CAUGHT, EncounterStatus.MISSED,
    EncounterStatus.FLED, EncounterStatus.FAINTED,
})


@dataclass(frozen=True)
class Ruleset:
    limited_encounters: bool = True
    mandatory_nicknames: bool = True


@dataclass(frozen=True)
class EncounterRecord:
    area_id: str
    status: EncounterStatus
    species_id: int | None = None
    nickname: str | None = None
    method: str | None = None
    level: int | None = None
    source: EncounterSource = EncounterSource.WILD
    notes: str | None = None


@dataclass(frozen=True)
class RunHistory:
    encounters: tuple[EncounterRecord, ...] = ()
    defeated_trainer_ids: frozenset[str] = frozenset()

    def encounter_for_area(self, area_id: str) -> EncounterRecord | None:
        matches = [record for record in self.encounters if record.area_id == area_id]
        if len(matches) > 1:
            raise ValueError(f"history has multiple first-encounter records for {area_id}")
        return matches[0] if matches else None


@dataclass(frozen=True)
class RuleNotification:
    code: str
    severity: str
    message: str
    area_id: str | None = None


@dataclass(frozen=True)
class AreaGuidance:
    area_id: str
    map_id: int
    map_name: str
    connection_direction: str | None
    encounters: tuple[dict[str, object], ...]
    items: tuple[dict[str, object], ...]
    encounter_available: bool | None
    progression_accessible: bool
    blocked_reason: str | None = None


@dataclass(frozen=True)
class LocationGuidance:
    current_location: dict[str, object]
    nearby_areas: tuple[AreaGuidance, ...]
    next_trainer: TrainerSummary | None
    reachable_trainers: tuple[TrainerSummary, ...]
    progression_objective: dict[str, object] | None
    items_here: tuple[dict[str, object], ...]
    notifications: tuple[RuleNotification, ...]
    provenance: dict[str, str]
    limitations: tuple[str, ...]
    completed_story_events: tuple[str, ...] = ()
    blocked_routes: tuple[dict[str, object], ...] = ()


PROGRESSION_MILESTONES = (
    ("brock", 0x36, "brock", "Boulder", "EVENT_BEAT_BROCK", 14, "Pewter Gym"),
    ("misty", 0x41, "misty", "Cascade", "EVENT_BEAT_MISTY", 21, "Cerulean Gym"),
    ("lt_surge", 0x5C, "lt_surge", "Thunder", "EVENT_BEAT_LT_SURGE", 24, "Vermilion Gym"),
    ("erika", 0x86, "erika", "Rainbow", "EVENT_BEAT_ERIKA", 29, "Celadon Gym"),
    ("koga", 0x9D, "koga", "Soul", "EVENT_BEAT_KOGA", 43, "Fuchsia Gym"),
    ("sabrina", 0xB2, "sabrina", "Marsh", "EVENT_BEAT_SABRINA", 43, "Saffron Gym"),
    ("blaine", 0xA6, "blaine", "Volcano", "EVENT_BEAT_BLAINE", 47, "Cinnabar Gym"),
    ("giovanni", 0x2D, "giovanni", "Earth", "EVENT_BEAT_VIRIDIAN_GYM_GIOVANNI", 50, "Viridian Gym"),
    ("lorelei", 0xF5, "lorelei", None, "EVENT_BEAT_LORELEIS_ROOM_TRAINER_0", 56, "Lorelei's Room"),
    ("bruno", 0xF6, "bruno", None, "EVENT_BEAT_BRUNOS_ROOM_TRAINER_0", 58, "Bruno's Room"),
    ("agatha", 0xF7, "agatha", None, "EVENT_BEAT_AGATHAS_ROOM_TRAINER_0", 60, "Agatha's Room"),
    ("lance", 0x71, "lance", None, "EVENT_BEAT_LANCES_ROOM_TRAINER_0", 62, "Lance's Room"),
    ("champion", 0x78, "rival3", None, "EVENT_BEAT_CHAMPION_RIVAL", 65, "Champion's Room"),
)


def _active_milestone(state: SaveState, world: Gen1WorldDatabase) -> tuple | None:
    if getattr(state, "hall_of_fame_team_count", 0) > 0:
        return None
    for milestone in PROGRESSION_MILESTONES:
        _, _, _, badge, event, _, _ = milestone
        complete = badge in state.earned_badges if badge else world.event_is_set(state, event)
        if not complete:
            return milestone
    return None


def _area_access(area_id: str, state: SaveState, world: Gen1WorldDatabase) -> tuple[bool, str | None]:
    badge_requirements = {
        "route_3": ("Boulder", "Brock and the Boulder Badge"),
        "route_9": ("Cascade", "Misty and the Cascade Badge (for Cut)"),
        "route_10": ("Cascade", "Misty and the Cascade Badge (for Cut access)"),
    }
    if area_id in badge_requirements:
        badge, reason = badge_requirements[area_id]
        if badge not in state.earned_badges:
            return False, f"Blocked until {reason}."
    if area_id in {"route_23", "victory_road_1f", "victory_road_2f", "victory_road_3f", "indigo_plateau_lobby"}:
        if len(state.earned_badges) < 8:
            return False, "Blocked until all eight badges are earned."
    if area_id.startswith("cerulean_cave") and not world.event_is_set(state, "EVENT_BEAT_CHAMPION_RIVAL"):
        return False, "Blocked until the Champion has been defeated."
    return True, None


def validate_encounter_record(
    record: EncounterRecord,
    version: GameVersion,
    *,
    ruleset: Ruleset = Ruleset(),
    world: Gen1WorldDatabase | None = None,
) -> None:
    world = world or Gen1WorldDatabase()
    if not isinstance(record.status, EncounterStatus) or not isinstance(record.source, EncounterSource):
        raise TypeError("encounter status and source must use their enum types")
    if record.status is EncounterStatus.UNCLAIMED:
        if any(value is not None for value in (record.species_id, record.method, record.level, record.nickname)):
            raise ValueError("an unclaimed area cannot have encounter details")
        return
    if record.species_id is None or record.level is None:
        raise ValueError("an encounter record requires species_id and level")
    if not 1 <= record.level <= 100:
        raise ValueError("encounter level must be in 1..100")
    if record.status is EncounterStatus.CAUGHT and ruleset.mandatory_nicknames and not (record.nickname or "").strip():
        raise ValueError("a caught Pokémon requires a nickname under this ruleset")
    if record.source is EncounterSource.WILD:
        if not record.method:
            raise ValueError("a wild encounter requires an encounter method")
        matching = [
            choice for choice in world.encounter_choices(record.area_id, version)
            if choice.method == record.method and choice.species_id == record.species_id
        ]
        if not matching:
            raise ValueError("species/method is not available in this area and game version")
        if record.level not in matching[0].valid_levels:
            raise ValueError(
                f"level {record.level} is not valid for {matching[0].species_name} via {record.method} in {matching[0].map_name}"
            )
    elif record.method is not None:
        raise ValueError("gift, static, and trade records must not use a wild encounter method")


def build_location_guidance(
    state: SaveState,
    history: RunHistory,
    *,
    ruleset: Ruleset = Ruleset(),
    world: Gen1WorldDatabase | None = None,
) -> LocationGuidance:
    if not state.is_valid:
        raise ValueError("guidance requires a valid parsed save")
    if state.game_version is None:
        raise ValueError("guidance requires a declared Red/Blue run version")
    world = world or Gen1WorldDatabase()
    for record in history.encounters:
        validate_encounter_record(record, state.game_version, ruleset=ruleset, world=world)
    nearby_targets = [(state.current_map_id, None)] + [
        (connection["to_map_id"], connection["direction"])
        for connection in world.connected_maps(state.current_map_id)
    ]
    areas = []
    notifications = []
    automatic_defeated = world.defeated_trainer_ids(state, state.game_version)
    effective_defeated = automatic_defeated | history.defeated_trainer_ids
    blocked_routes = []
    for map_id, direction in nearby_targets:
        encounters = world.encounter_summaries(map_id, state.game_version)
        if not encounters:
            continue
        area_id = encounters[0].area_id
        prior = history.encounter_for_area(area_id)
        available = None if prior is None else not (
            ruleset.limited_encounters and prior.status in CONSUMING_STATUSES
        )
        if available is None:
            notifications.append(RuleNotification(
                "area_encounter_history_required", "warning",
                f"{get_map(map_id).display_name} encounter status is unknown; confirm whether its first encounter was already used.",
                area_id,
            ))
        elif available:
            notifications.append(RuleNotification(
                "area_encounter_available", "info",
                f"{get_map(map_id).display_name} still has an available first encounter.", area_id,
            ))
        else:
            notifications.append(RuleNotification(
                "area_encounter_consumed", "warning",
                f"Do not catch another Pokémon in {get_map(map_id).display_name}; its first encounter is already {prior.status.value}.",
                area_id,
            ))
        progression_accessible, blocked_reason = _area_access(area_id, state, world)
        areas.append(AreaGuidance(
            area_id=area_id, map_id=map_id, map_name=get_map(map_id).display_name,
            connection_direction=direction,
            encounters=tuple(asdict(encounter) for encounter in encounters),
            items=world.items_for_map(map_id, state.game_version, state=state),
            encounter_available=available,
            progression_accessible=progression_accessible,
            blocked_reason=blocked_reason,
        ))
        if not progression_accessible:
            blocked_routes.append({"area_id": area_id, "map_id": map_id, "reason": blocked_reason})
            notifications.append(RuleNotification(
                "area_progression_locked", "warning",
                f"{get_map(map_id).display_name}: {blocked_reason}", area_id,
            ))

    if ruleset.mandatory_nicknames:
        for mon in state.party:
            from gen1_save_parser.layout.gen1_species_index import get_species_name
            species_id = mon["species_id"] if isinstance(mon, dict) else mon.species_id
            nickname = mon["nickname"] if isinstance(mon, dict) else mon.nickname
            if nickname.casefold() == get_species_name(species_id).casefold():
                notifications.append(RuleNotification(
                    "missing_required_nickname", "violation",
                    f"{get_species_name(species_id)} appears to retain its default species name.",
                ))

    progression_objective = None
    progression_fallback_trainer = None
    milestone = _active_milestone(state, world)
    if milestone:
        objective_id, map_id, boss_class, badge, event_symbol, level_cap, location_name = milestone
        objective_trainers = [
            trainer for trainer in world.trainers_for_map(map_id, state.game_version)
            if trainer.get("party_selection") != "rival_starter"
            or trainer.get("rival_starter_id") == getattr(state, "rival_starter_id", None)
        ]
        objective_trainers.sort(key=lambda trainer: (
            trainer["trainer_class_id"] == boss_class,
            trainer.get("object_index", 0),
        ))
        summaries = tuple(
            world.trainer_summary(trainer, basis="mandatory_progression", state=state)
            for trainer in objective_trainers
        )
        summaries = tuple(
            replace(trainer, defeated=True) if trainer.trainer_id in effective_defeated else trainer
            for trainer in summaries
        )
        remaining = [trainer for trainer in summaries if trainer.trainer_id not in effective_defeated]
        progression_fallback_trainer = remaining[0] if remaining else None
        progression_objective = {
            "objective_id": f"defeat_{objective_id}",
            "location_id": get_map(map_id).stable_id,
            "location_name": location_name,
            "required_badge": badge,
            "boss": objective_id.replace("_", " ").title(),
            "completion_event": event_symbol,
            "level_cap": level_cap,
            "trainers": [asdict(trainer) for trainer in summaries],
        }
        for mon in state.party:
            species_id = mon["species_id"] if isinstance(mon, dict) else mon.species_id
            level = mon["level"] if isinstance(mon, dict) else mon.level
            nickname = mon["nickname"] if isinstance(mon, dict) else mon.nickname
            if level > level_cap:
                from gen1_save_parser.layout.gen1_species_index import get_species_name
                notifications.append(RuleNotification(
                    "level_cap_exceeded", "violation",
                    f"{nickname or get_species_name(species_id)} is level {level}, above the active {location_name} cap of {level_cap}.",
                ))
    accessible_connected_map_ids = frozenset(
        connection["to_map_id"]
        for connection in world.connected_maps(state.current_map_id)
        if _area_access(get_map(connection["to_map_id"]).stable_id, state, world)[0]
    )
    reachable_trainers = world.reachable_trainer_candidates(
        map_id=state.current_map_id, version=state.game_version,
        player_x=state.player_x, player_y=state.player_y,
        defeated_trainer_ids=effective_defeated,
        allowed_connected_map_ids=accessible_connected_map_ids,
        state=state,
    )
    next_trainer = reachable_trainers[0] if reachable_trainers else None
    if next_trainer is None:
        next_trainer = progression_fallback_trainer
        reachable_trainers = (progression_fallback_trainer,) if progression_fallback_trainer else ()
    return LocationGuidance(
        current_location={
            "map_id": state.current_map_id, "location_id": state.location_id,
            "display_name": state.location_name, "player_x": state.player_x, "player_y": state.player_y,
        },
        nearby_areas=tuple(areas), next_trainer=next_trainer,
        reachable_trainers=reachable_trainers,
        progression_objective=progression_objective,
        items_here=world.items_for_map(state.current_map_id, state.game_version, state=state),
        notifications=tuple(notifications), provenance=world.source_provenance,
        limitations=tuple(world.data["limitations"]) + (
            "Within-map trainer ordering uses object/script order and does not yet pathfind around walls or warps.",
            "Encounter history is user-maintained; Pokédex ownership is not treated as proof of a route claim.",
        ),
        completed_story_events=tuple(sorted(
            symbol for symbol, bit in world.data["event_constants"].items()
            if bit in getattr(state, "event_flags", ())
        )),
        blocked_routes=tuple(blocked_routes),
    )


def build_location_guidance_from_snapshot(
    snapshot: object,
    history: RunHistory,
    *,
    ruleset: Ruleset = Ruleset(),
    world: Gen1WorldDatabase | None = None,
) -> LocationGuidance:
    """Rebuild guidance from an immutable latest snapshot without retaining the .sav."""
    from types import SimpleNamespace

    state = snapshot.save_state
    location = state["location"]
    world_state = state.get("world_state", {})
    adapter = SimpleNamespace(
        is_valid=state["status"] in ("valid", "valid_with_warnings"),
        game_version=GameVersion(state["game_version"]),
        current_map_id=location["raw_map_id"],
        player_x=location.get("player_x"),
        player_y=location.get("player_y"),
        location_id=location["location_id"],
        location_name=location["display_name"],
        party=state["party"],
        earned_badges=state["badges"]["earned"],
        player_starter_id=world_state.get("player_starter_id"),
        rival_starter_id=world_state.get("rival_starter_id"),
        hall_of_fame_team_count=world_state.get("hall_of_fame_team_count", 0),
        toggleable_object_flags=frozenset(world_state.get("toggleable_object_flags", ())),
        obtained_hidden_item_flags=frozenset(world_state.get("obtained_hidden_item_flags", ())),
        event_flags=frozenset(world_state.get("event_flags", ())),
    )
    return build_location_guidance(adapter, history, ruleset=ruleset, world=world)
