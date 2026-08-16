"""JSON-ready dashboard projection for the local web interface."""

from __future__ import annotations

from dataclasses import asdict

from gen1_save_parser.mechanics import calculate_party_stats, decode_dvs
from gen1_save_parser.layout.gen1_battle_data import get_species_base_data
from gen1_save_parser.layout.gen1_maps import get_map
from gen1_save_parser.layout.gen1_species_index import get_species_name
from gen1_save_parser.models import SaveState

from .reference import Gen1WorldDatabase
from .rules import PROGRESSION_MILESTONES, RunHistory, build_location_guidance


ITEM_ACCESS_RULES = {
    "route_2": {
        "requirement": "Requires Cut: Cascade Badge and a party Pokémon that knows Cut.",
        "source": "https://bulbapedia.bulbagarden.net/wiki/Kanto_Route_2",
        "capability": "cut",
    },
}


# Exact full-map renders are registered by map ID. Map dimensions themselves
# come from the generated pret/pokered registry, not from the image dimensions.
EXACT_MAP_VIEWS = {
    0x03: {
        "asset": "assets/maps/cerulean-city-rby.png",
        "source_url": "https://archives.bulbagarden.net/wiki/File:Cerulean_City_RBY.png",
        "source_label": "Cerulean City RBY map · Bulbagarden Archives",
    },
}


def _map_view_payload(state: SaveState) -> dict[str, object]:
    definition = get_map(state.current_map_id)
    exact = EXACT_MAP_VIEWS.get(state.current_map_id)
    if definition is None or definition.width_blocks <= 0 or definition.height_blocks <= 0:
        return {"precision": "unavailable"}

    # Red/Blue map headers measure 2x2 metatile blocks. Player X/Y values are
    # walkable tile coordinates, so each declared block contributes two axes.
    width_tiles = definition.width_blocks * 2
    height_tiles = definition.height_blocks * 2
    payload: dict[str, object] = {
        "width_blocks": definition.width_blocks,
        "height_blocks": definition.height_blocks,
        "width_tiles": width_tiles,
        "height_tiles": height_tiles,
    }
    if exact is None:
        payload.update({
            "precision": "regional_overview",
            "asset": "assets/kanto-town-map-rby.png",
            "source_label": "Pokémon Red/Blue Kanto Town Map",
        })
        return payload

    if not (0 <= state.player_x < width_tiles and 0 <= state.player_y < height_tiles):
        return {**payload, "precision": "invalid_coordinates", **exact}
    return {
        **payload,
        **exact,
        "precision": "exact_tile",
        "marker_left_percent": (state.player_x + 0.5) / width_tiles * 100,
        "marker_top_percent": (state.player_y + 0.5) / height_tiles * 100,
    }


def _item_payload(item: dict[str, object], capabilities: dict[str, bool]) -> dict[str, object]:
    payload = dict(item)
    rule = ITEM_ACCESS_RULES.get(str(item["area_id"]))
    if rule is None:
        payload["access_status"] = "unverified"
        payload["access_requirement"] = "Exact walking-path prerequisites have not been verified yet."
        payload["access_source"] = payload.get("source_ref")
    else:
        available = capabilities[rule["capability"]]
        payload["access_status"] = "available" if available else "locked"
        payload["access_requirement"] = rule["requirement"]
        payload["access_source"] = rule["source"]
    return payload


def _mon_payload(mon: object) -> dict[str, object]:
    species_id = mon.species_id
    species = get_species_base_data(species_id)
    return {
        "species_id": species_id,
        "dex_number": species.dex_number,
        "species_name": species.display_name,
        "nickname": mon.nickname,
        "level": mon.level,
        "current_hp": mon.current_hp,
        "max_hp": getattr(mon, "max_hp", mon.current_hp),
        "types": list(dict.fromkeys(mon.type_names)),
        "moves": [asdict(move) for move in mon.move_details],
        "status_conditions": list(mon.status_conditions),
    }


def _box_mon_payload(mon: object) -> dict[str, object]:
    species = get_species_base_data(mon.species_id)
    stats = calculate_party_stats(species, mon.dvs, mon.stat_exp, mon.level)
    stat_names = ("hp", "attack", "defense", "speed", "special")
    return {
        "species_id": mon.species_id,
        "dex_number": species.dex_number,
        "species_name": species.display_name,
        "nickname": mon.nickname,
        "level": mon.level,
        "current_hp": mon.current_hp,
        "calculated_max_hp": stats["hp"],
        "types": list(dict.fromkeys(mon.type_names)),
        "moves": [asdict(move) for move in mon.move_details],
        "status_conditions": list(mon.status_conditions),
        "original_trainer_name": mon.original_trainer_name,
        "original_trainer_id": mon.ot_id,
        "experience": mon.exp,
        "experience_to_next_level": mon.experience_to_next_level,
        "dvs": decode_dvs(mon.dvs),
        "stat_experience": dict(zip(stat_names, mon.stat_exp)),
        "calculated_stats": stats,
        "stats_evidence": "calculated_from_stored_level_dvs_stat_experience_and_canonical_base_stats",
    }


def _trainer_payload(summary: object | None) -> dict[str, object] | None:
    if summary is None:
        return None
    data = asdict(summary)
    for member in data["party"]:
        member["dex_number"] = get_species_base_data(member["species_id"]).dex_number
    return data


def build_dashboard_payload(
    state: SaveState,
    history: RunHistory | None = None,
    *,
    world: Gen1WorldDatabase | None = None,
) -> dict[str, object]:
    if not state.is_valid or state.game_version is None:
        raise ValueError("dashboard payload requires a valid save and declared game version")
    history = history or RunHistory()
    world = world or Gen1WorldDatabase()
    guidance = build_location_guidance(state, history, world=world)
    defeated_ids = world.defeated_trainer_ids(state, state.game_version) | history.defeated_trainer_ids
    capabilities = {
        "cut": "Cascade" in state.earned_badges and any(
            move.stable_id == "cut" for mon in state.party for move in mon.move_details
        ),
    }

    areas = []
    for area in guidance.nearby_areas:
        encounters = []
        for encounter in area.encounters:
            item = dict(encounter)
            item["dex_number"] = get_species_base_data(item["species_id"]).dex_number
            encounters.append(item)
        areas.append({
            "area_id": area.area_id,
            "map_id": area.map_id,
            "map_name": area.map_name,
            "direction": area.connection_direction,
            "encounter_status": (
                "unknown" if area.encounter_available is None
                else "available" if area.encounter_available else "consumed"
            ),
            "progression_accessible": area.progression_accessible,
            "blocked_reason": area.blocked_reason,
            "encounters": encounters,
            "items": [_item_payload(item, capabilities) for item in area.items],
        })

    objective = dict(guidance.progression_objective) if guidance.progression_objective else None
    if objective:
        objective["trainers"] = [
            {
                **trainer,
                "party": [
                    {
                        **member,
                        "dex_number": get_species_base_data(member["species_id"]).dex_number,
                    }
                    for member in trainer["party"]
                ],
            }
            for trainer in objective["trainers"]
        ]
        objective["next_trainer"] = _trainer_payload(guidance.next_trainer)
    completed_milestones = 13 if state.hall_of_fame_team_count else next(
        (index for index, milestone in enumerate(PROGRESSION_MILESTONES)
         if objective and objective["objective_id"] == f"defeat_{milestone[0]}"),
        13 if objective is None else len(state.earned_badges),
    )

    default_species_names = {
        get_species_name(mon.species_id).casefold() for mon in state.party
        if mon.nickname.casefold() == get_species_name(mon.species_id).casefold()
    }
    encounter_catalog = []
    encounter_area_names: dict[str, str] = {}
    for area in world.encounter_areas(state.game_version):
        encounter_area_names[area.area_id] = area.map_name
        choices = []
        for choice in world.encounter_choices(area.area_id, state.game_version):
            choices.append({
                **asdict(choice),
                "dex_number": get_species_base_data(choice.species_id).dex_number,
            })
        encounter_catalog.append({**asdict(area), "choices": choices})
    encounter_history = []
    for record in history.encounters:
        species = get_species_base_data(record.species_id) if record.species_id is not None else None
        encounter_history.append({
            "area_id": record.area_id,
            "map_name": encounter_area_names.get(record.area_id, record.area_id.replace("_", " ").title()),
            "status": record.status.value,
            "species_id": record.species_id,
            "species_name": species.display_name if species else None,
            "dex_number": species.dex_number if species else None,
            "nickname": record.nickname,
            "method": record.method,
            "level": record.level,
            "source": record.source.value,
            "notes": record.notes,
        })
    caught_records = [record for record in encounter_history if record["status"] == "caught"]
    matched_areas: set[str] = set()
    party_payload = []
    for mon in state.party:
        payload = _mon_payload(mon)
        match = next((
            record for record in caught_records
            if record["area_id"] not in matched_areas
            and record.get("nickname")
            and str(record["nickname"]).casefold() == mon.nickname.casefold()
        ), None)
        match_basis = "nickname"
        if match is None:
            species_matches = [
                record for record in caught_records
                if record["area_id"] not in matched_areas
                and record.get("species_id") == mon.species_id
            ]
            match = species_matches[0] if len(species_matches) == 1 else None
            match_basis = "unique_species"
        if match is not None:
            matched_areas.add(str(match["area_id"]))
            payload["encounter_origin"] = {
                "area_id": match["area_id"], "map_name": match["map_name"],
                "caught_level": match["level"], "method": match["method"],
                "source": match["source"], "recorded_species_name": match["species_name"],
                "match_basis": match_basis, "evidence": "user_confirmed_manual_history",
            }
        else:
            payload["encounter_origin"] = None
        payload["met_data_source"] = "not_stored_in_generation_i_save"
        party_payload.append(payload)
    cap = objective["level_cap"] if objective else None
    return {
        "schema_version": 1,
        "parser": {
            "status": state.status.value,
            "diagnostics": [
                {
                    "code": item.code,
                    "severity": item.severity.value,
                    "message": item.message,
                    "offset": item.offset,
                }
                for item in state.diagnostics
            ],
        },
        "trainer": {
            "name": state.player_name,
            "trainer_id": state.player_id,
            "rival_name": state.rival_name,
            "version": state.game_version.value,
            "money": state.money,
            "pokedex_owned": len(state.pokedex_owned),
            "pokedex_seen": len(state.pokedex_seen),
            "hall_of_fame_teams": state.hall_of_fame_team_count,
        },
        "location": {
            "map_id": state.current_map_id,
            "location_id": state.location_id,
            "name": state.location_name,
            "x": state.player_x,
            "y": state.player_y,
            "map_view": _map_view_payload(state),
        },
        "party": party_payload,
        "boxes": {
            "initialized": state.boxes_initialized,
            "current_box_index": state.current_box_index,
            "observed_pokemon": sum(len(box.members) for box in state.pc_boxes),
            "capacity_per_box": 20,
            "box_count": len(state.pc_boxes),
            "entries": [
                {
                    "index": box.index,
                    "display_number": box.index + 1,
                    "status": box.status.value,
                    "is_current": box.index == state.current_box_index,
                    "checksum_verified": box.checksum_verified,
                    "pokemon_count": len(box.members),
                    "members": [_box_mon_payload(mon) for mon in box.members],
                }
                for box in state.pc_boxes
            ],
            "accuracy_note": (
                "All initialized boxes were checksum-validated. Boxed battle stats are calculated because "
                "Generation I stores their inputs, not the final five battle-stat values."
                if state.boxes_initialized else
                "The save's box-storage initialization flag is not set. The current-box cache is parsed; "
                "other boxes marked uninitialized are not treated as known-empty boxes."
            ),
        },
        "inventory": {
            "bag": [
                {
                    "item_id": item.item_id,
                    "stable_id": item.stable_id,
                    "display_name": item.display_name,
                    "quantity": item.quantity,
                }
                for item in state.bag_items
            ],
            "pc": [
                {
                    "item_id": item.item_id,
                    "stable_id": item.stable_id,
                    "display_name": item.display_name,
                    "quantity": item.quantity,
                }
                for item in state.pc_items
            ],
        },
        "badges": list(state.earned_badges),
        "progress": {"completed": completed_milestones, "total": 13},
        "objective": objective,
        "next_trainer": _trainer_payload(guidance.next_trainer),
        "reachable_trainers": [_trainer_payload(trainer) for trainer in guidance.reachable_trainers],
        "encounter_catalog": encounter_catalog,
        "encounter_history": encounter_history,
        "areas": areas,
        "items_here": [_item_payload(item, capabilities) for item in guidance.items_here],
        "field_capabilities": capabilities,
        "blocked_routes": list(guidance.blocked_routes),
        "completed_story_events": list(guidance.completed_story_events),
        "defeated_trainer_count": len(defeated_ids),
        "notifications": [asdict(item) for item in guidance.notifications],
        "checks": [
            {
                "code": "nicknames",
                "state": "ok" if not default_species_names else "violation",
                "label": "All party Pokémon nicknamed" if not default_species_names else "Default species names detected",
                "value": "OK" if not default_species_names else str(len(default_species_names)),
            },
            {
                "code": "level_cap",
                "state": "ok" if cap is None or all(mon.level <= cap for mon in state.party) else "violation",
                "label": "Party within active level cap" if cap is not None else "No active boss level cap",
                "value": "OK" if cap is None or all(mon.level <= cap for mon in state.party) else f"CAP {cap}",
            },
            {
                "code": "encounter_history",
                "state": "warning" if any(area["encounter_status"] == "unknown" for area in areas) else "ok",
                "label": "Nearby encounter history",
                "value": "CONFIRM" if any(area["encounter_status"] == "unknown" for area in areas) else "KNOWN",
            },
            {
                "code": "route_access",
                "state": "warning" if guidance.blocked_routes else "ok",
                "label": "Nearby progression routes",
                "value": f"{len(guidance.blocked_routes)} BLOCKED" if guidance.blocked_routes else "OPEN",
            },
        ],
        "limitations": list(guidance.limitations),
        "provenance": guidance.provenance,
    }
