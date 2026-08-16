import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from gen1_save_parser import GameVersion, parse_save_bytes
from gen1_save_parser.checksum import calculate_main_checksum
from gen1_save_parser.layout.gen1_main_data import (
    BADGES, EVENT_FLAGS, MAIN_DATA_CHECKSUM,
)
from nuzlocke_app import (
    EncounterRecord,
    EncounterSource,
    EncounterStatus,
    FileSnapshotRepository,
    Gen1WorldDatabase,
    RunHistory,
    RunProfile,
    build_location_guidance,
    validate_encounter_record,
)


FIXTURE = Path(__file__).parent / "fixtures" / "pokemon_blue.sav"
COMPLETED_ONLINE_FIXTURE = Path(__file__).parent / "fixtures" / "pokemon_blue_completed_online.sav"


class WorldDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = Gen1WorldDatabase()

    def test_generated_registry_is_pinned_and_complete(self) -> None:
        self.assertEqual(self.world.source_provenance, {
            "source": "pret/pokered",
            "commit": "0cd19d3b877b7dc66d12c7050bed9a7f38154d4b",
            "sha256": "f55b8e48559cd4cdef790ada8c9ef70aa76673373a20618706e1c8e2a300f75c",
        })
        self.assertEqual(len(self.world.data["encounters"]), 1378)
        self.assertEqual(len(self.world.data["trainers"]), 674)
        self.assertEqual(len(self.world.data["items"]), 262)
        self.assertEqual(len(self.world.data["connections"]), 78)
        self.assertEqual(self.world.trainer_battle_data["source_commit"], "0cd19d3b877b7dc66d12c7050bed9a7f38154d4b")
        self.assertEqual(len(self.world.trainer_battle_data["species"]), 151)
        self.assertEqual(self.world.trainer_battle_data["trainer_dvs"], {
            "hp": 8, "attack": 9, "defense": 8, "speed": 8, "special": 8,
        })

    def test_route_2_is_version_specific(self) -> None:
        red = {item.species_name for item in self.world.encounter_summaries(0x0D, GameVersion.RED)}
        blue = {item.species_name for item in self.world.encounter_summaries(0x0D, GameVersion.BLUE)}
        self.assertEqual(red, {"Pidgey", "Rattata", "Weedle"})
        self.assertEqual(blue, {"Pidgey", "Rattata", "Caterpie"})

    def test_visible_and_hidden_items_have_exact_tile_coordinates(self) -> None:
        items = self.world.items_for_map(0x33, GameVersion.BLUE)
        self.assertIn(("Antidote", False, 25, 11), {
            (item["item_name"], item["hidden"], item["x"], item["y"]) for item in items
        })
        self.assertIn(("Potion", True, 1, 18), {
            (item["item_name"], item["hidden"], item["x"], item["y"]) for item in items
        })

    def test_every_item_and_persistent_trainer_has_a_save_flag_mapping(self) -> None:
        visible = [item for item in self.world.data["items"] if not item["hidden"]]
        self.assertTrue(all(item.get("toggleable_object_flag_index") is not None for item in visible))
        unresolved = [
            trainer for trainer in self.world.data["trainers"]
            if trainer.get("event_flag_index") is None
        ]
        self.assertEqual({trainer["area_id"] for trainer in unresolved}, {"ss_anne_2f"})

    def test_map_specific_super_rod_table_is_preserved(self) -> None:
        route_4 = self.world.encounter_summaries(0x0F, GameVersion.BLUE)
        super_rod = {
            (entry.species_name, entry.levels, entry.slot_weight, entry.slot_weight_denominator)
            for entry in route_4 if entry.method == "super_rod"
        }
        self.assertEqual(super_rod, {
            ("Psyduck", (15,), 1, 3),
            ("Goldeen", (15,), 1, 3),
            ("Krabby", (15,), 1, 3),
        })


class LocationGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.state = parse_save_bytes(FIXTURE.read_bytes(), expected_version=GameVersion.BLUE)
        cls.world = Gen1WorldDatabase()

    def test_pewter_guidance_prioritizes_mandatory_gym_before_route_3(self) -> None:
        guidance = build_location_guidance(self.state, RunHistory())
        self.assertEqual((self.state.player_x, self.state.player_y), (13, 27))
        self.assertEqual({area.map_name for area in guidance.nearby_areas}, {"Route 2", "Route 3"})
        route_3 = next(area for area in guidance.nearby_areas if area.area_id == "route_3")
        self.assertIn(("Jigglypuff", (3, 5, 7), ("Normal",)), {
            (entry["species_name"], entry["levels"], entry["type_names"])
            for entry in route_3.encounters
        })
        self.assertFalse(route_3.progression_accessible)
        self.assertIn("area_progression_locked", {item.code for item in guidance.notifications})
        self.assertEqual(guidance.progression_objective["location_name"], "Pewter Gym")
        self.assertEqual(guidance.progression_objective["level_cap"], 14)
        trainer = guidance.next_trainer
        self.assertEqual((trainer.map_name, trainer.trainer_class, trainer.x, trainer.y), ("Pewter Gym", "Jr. Trainer♂", 3, 6))
        self.assertEqual(
            [(member["species_name"], member["level"], member["types"]) for member in trainer.party],
            [("Diglett", 11, ["Ground"]), ("Sandshrew", 11, ["Ground"])],
        )
        brock = guidance.progression_objective["trainers"][1]
        self.assertEqual(
            [(member["species_name"], member["level"]) for member in brock["party"]],
            [("Geodude", 12), ("Onix", 14)],
        )
        self.assertEqual([move["move_name"] for move in brock["party"][1]["moves"]], ["Tackle", "Screech", "Bide"])

    def test_early_fixture_does_not_claim_late_viridian_events(self) -> None:
        guidance = build_location_guidance(self.state, RunHistory(), world=self.world)
        events = set(guidance.completed_story_events)
        self.assertNotIn("EVENT_GOT_TM42", events)
        self.assertNotIn("EVENT_VIRIDIAN_GYM_OPEN", events)
        self.assertIn("EVENT_GOT_STARTER", events)
        self.assertIn("EVENT_BATTLED_RIVAL_IN_OAKS_LAB", events)

    def test_consumed_route_generates_do_not_catch_warning(self) -> None:
        history = RunHistory(encounters=(EncounterRecord(
            "route_2", EncounterStatus.CAUGHT, species_id=0x24, nickname="Birb", method="grass", level=3,
        ),))
        guidance = build_location_guidance(self.state, history)
        route_2 = next(area for area in guidance.nearby_areas if area.area_id == "route_2")
        self.assertFalse(route_2.encounter_available)
        self.assertIn("area_encounter_consumed", {item.code for item in guidance.notifications})

    def test_pokedex_is_not_used_as_encounter_history(self) -> None:
        guidance = build_location_guidance(self.state, RunHistory())
        route_2 = next(area for area in guidance.nearby_areas if area.area_id == "route_2")
        self.assertIsNone(route_2.encounter_available)
        self.assertIn("area_encounter_history_required", {item.code for item in guidance.notifications})

    def test_user_confirmed_unclaimed_route_is_available(self) -> None:
        history = RunHistory(encounters=(EncounterRecord("route_3", EncounterStatus.UNCLAIMED),))
        guidance = build_location_guidance(self.state, history)
        route_3 = next(area for area in guidance.nearby_areas if area.area_id == "route_3")
        self.assertTrue(route_3.encounter_available)
        self.assertFalse(route_3.progression_accessible)

    def test_manual_entry_options_and_validation_use_version_correct_data(self) -> None:
        world = Gen1WorldDatabase()
        choices = world.encounter_choices("route_2", GameVersion.BLUE)
        self.assertIn("route_2", {area.area_id for area in world.encounter_areas(GameVersion.BLUE)})
        self.assertIn(("Caterpie", "grass", (3, 4, 5)), {
            (choice.species_name, choice.method, choice.valid_levels) for choice in choices
        })
        valid = EncounterRecord(
            "route_2", EncounterStatus.CAUGHT, species_id=0x24, nickname="Birb",
            method="grass", level=3, source=EncounterSource.WILD,
        )
        validate_encounter_record(valid, GameVersion.BLUE, world=world)
        with self.assertRaises(ValueError):
            validate_encounter_record(
                EncounterRecord(
                    "route_2", EncounterStatus.CAUGHT, species_id=0x24, nickname="Birb",
                    method="grass", level=9,
                ),
                GameVersion.BLUE,
                world=world,
            )

    def test_pewter_level_cap_violation_is_reported(self) -> None:
        state = deepcopy(self.state)
        state.party[0].level = 15
        guidance = build_location_guidance(state, RunHistory())
        self.assertIn("level_cap_exceeded", {item.code for item in guidance.notifications})

    def test_nearest_route_trainer_takes_priority_over_later_gym_objective(self) -> None:
        state = deepcopy(self.state)
        state.badges = 1
        state.earned_badges = ["Boulder"]
        state.current_map_id = 0x0E
        state.location_id = "route_3"
        state.location_name = "Route 3"
        state.player_x = 5
        state.player_y = 5

        guidance = build_location_guidance(state, RunHistory(), world=self.world)

        self.assertEqual(guidance.progression_objective["objective_id"], "defeat_misty")
        self.assertEqual(
            (guidance.next_trainer.map_name, guidance.next_trainer.trainer_class),
            ("Route 3", "Bug Catcher"),
        )
        self.assertEqual(guidance.next_trainer.selection_basis, "same_map_manhattan_distance")

    def test_unbeaten_cerulean_rival_precedes_story_gated_rocket(self) -> None:
        state = deepcopy(self.state)
        state.badges = 0b11
        state.earned_badges = ["Boulder", "Cascade"]
        state.current_map_id = 0x03
        state.location_id = "cerulean_city"
        state.location_name = "Cerulean City"
        state.player_x = 19
        state.player_y = 18
        state.rival_starter_id = 0xB1
        state.event_flags = state.event_flags - {
            self.world.data["event_constants"]["EVENT_BEAT_CERULEAN_RIVAL"],
            self.world.data["event_constants"]["EVENT_GOT_SS_TICKET"],
        }

        guidance = build_location_guidance(state, RunHistory(), world=self.world)

        self.assertEqual(guidance.next_trainer.trainer_class, "Rival")
        self.assertEqual(guidance.next_trainer.map_name, "Cerulean City")
        self.assertEqual(
            [(member["species_name"], member["level"]) for member in guidance.next_trainer.party],
            [("Pidgeotto", 18), ("Abra", 15), ("Rattata", 15), ("Squirtle", 17)],
        )
        self.assertEqual(guidance.next_trainer.party[0]["stats"], {
            "hp": 53, "attack": 29, "defense": 27, "speed": 33, "special": 25,
        })
        self.assertEqual(
            [move["move_name"] for move in guidance.next_trainer.party[3]["moves"]],
            ["Tackle", "Tail Whip", "Bubble", "Water Gun"],
        )
        self.assertEqual(guidance.reachable_trainers[0].trainer_id, guidance.next_trainer.trainer_id)
        self.assertGreater(len(guidance.reachable_trainers), 1)
        self.assertEqual(guidance.progression_objective["objective_id"], "defeat_lt_surge")

    def test_cerulean_rocket_is_not_recommended_before_ticket_event(self) -> None:
        state = deepcopy(self.state)
        state.current_map_id = 0x03
        state.location_id = "cerulean_city"
        state.location_name = "Cerulean City"
        state.player_x = 30
        state.player_y = 8
        state.rival_starter_id = 0xB1
        state.event_flags = state.event_flags | {
            self.world.data["event_constants"]["EVENT_BEAT_CERULEAN_RIVAL"],
        }
        state.event_flags = state.event_flags - {
            self.world.data["event_constants"]["EVENT_GOT_SS_TICKET"],
        }

        guidance = build_location_guidance(state, RunHistory(), world=self.world)

        self.assertNotEqual(guidance.next_trainer.trainer_id, "cerulean_city:1:rocket:5")

    def test_save_event_bit_selects_actual_next_undefeated_gym_trainer(self) -> None:
        data = bytearray(FIXTURE.read_bytes())
        pewter_trainer_bit = self.world.data["event_constants"]["EVENT_BEAT_PEWTER_GYM_TRAINER_0"]
        data[EVENT_FLAGS + pewter_trainer_bit // 8] |= 1 << (pewter_trainer_bit % 8)
        data[MAIN_DATA_CHECKSUM] = calculate_main_checksum(data)
        state = parse_save_bytes(bytes(data), expected_version=GameVersion.BLUE)
        guidance = build_location_guidance(state, RunHistory(), world=self.world)
        self.assertEqual(guidance.next_trainer.trainer_class, "Brock")
        self.assertTrue(guidance.progression_objective["trainers"][0]["defeated"])

    def test_badge_advances_cap_and_unlocks_route_3(self) -> None:
        data = bytearray(FIXTURE.read_bytes())
        data[BADGES] |= 1
        data[MAIN_DATA_CHECKSUM] = calculate_main_checksum(data)
        state = parse_save_bytes(bytes(data), expected_version=GameVersion.BLUE)
        guidance = build_location_guidance(state, RunHistory(), world=self.world)
        self.assertEqual((guidance.progression_objective["objective_id"], guidance.progression_objective["level_cap"]), ("defeat_misty", 21))
        route_3 = next(area for area in guidance.nearby_areas if area.area_id == "route_3")
        self.assertTrue(route_3.progression_accessible)

    def test_fixture_item_flags_distinguish_collected_visible_and_hidden_items(self) -> None:
        forest = self.world.items_for_map(0x33, GameVersion.BLUE, state=self.state)
        antidote = next(item for item in forest if item["item_name"] == "Antidote" and not item["hidden"])
        hidden_potion = next(item for item in forest if item["item_name"] == "Potion" and item["hidden"])
        self.assertTrue(antidote["collected"])
        self.assertFalse(hidden_potion["collected"])

    def test_elite_four_events_advance_objective_and_select_champion_team(self) -> None:
        state = deepcopy(self.state)
        state.badges = 0xFF
        state.earned_badges = ["Boulder", "Cascade", "Thunder", "Rainbow", "Soul", "Marsh", "Volcano", "Earth"]
        completed = {
            self.world.data["event_constants"][symbol] for symbol in (
                "EVENT_BEAT_LORELEIS_ROOM_TRAINER_0", "EVENT_BEAT_BRUNOS_ROOM_TRAINER_0",
                "EVENT_BEAT_AGATHAS_ROOM_TRAINER_0", "EVENT_BEAT_LANCES_ROOM_TRAINER_0",
            )
        }
        state.event_flags = state.event_flags | completed
        guidance = build_location_guidance(state, RunHistory(), world=self.world)
        self.assertEqual(guidance.progression_objective["objective_id"], "defeat_champion")
        self.assertEqual(guidance.progression_objective["level_cap"], 65)
        champion = guidance.progression_objective["trainers"][0]
        self.assertEqual(champion["party"][-1]["species_name"], "Blastoise")
        self.assertIn("Sky Attack", [move["move_name"] for move in champion["party"][0]["moves"]])
        self.assertIn("Blizzard", [move["move_name"] for move in champion["party"][-1]["moves"]])
        self.assertNotEqual(guidance.next_trainer.map_name, "Champion's Room")

    def test_all_boss_milestones_advance_in_order(self) -> None:
        state = deepcopy(self.state)
        state.badges = 0
        state.earned_badges = []
        state.event_flags = frozenset()
        state.hall_of_fame_team_count = 0
        sequence = (
            ("brock", "Boulder", "EVENT_BEAT_BROCK", 14),
            ("misty", "Cascade", "EVENT_BEAT_MISTY", 21),
            ("lt_surge", "Thunder", "EVENT_BEAT_LT_SURGE", 24),
            ("erika", "Rainbow", "EVENT_BEAT_ERIKA", 29),
            ("koga", "Soul", "EVENT_BEAT_KOGA", 43),
            ("sabrina", "Marsh", "EVENT_BEAT_SABRINA", 43),
            ("blaine", "Volcano", "EVENT_BEAT_BLAINE", 47),
            ("giovanni", "Earth", "EVENT_BEAT_VIRIDIAN_GYM_GIOVANNI", 50),
            ("lorelei", None, "EVENT_BEAT_LORELEIS_ROOM_TRAINER_0", 56),
            ("bruno", None, "EVENT_BEAT_BRUNOS_ROOM_TRAINER_0", 58),
            ("agatha", None, "EVENT_BEAT_AGATHAS_ROOM_TRAINER_0", 60),
            ("lance", None, "EVENT_BEAT_LANCES_ROOM_TRAINER_0", 62),
            ("champion", None, "EVENT_BEAT_CHAMPION_RIVAL", 65),
        )
        for boss, badge, event, cap in sequence:
            guidance = build_location_guidance(state, RunHistory(), world=self.world)
            self.assertEqual((guidance.progression_objective["objective_id"], guidance.progression_objective["level_cap"]), (f"defeat_{boss}", cap))
            if badge:
                state.earned_badges.append(badge)
            else:
                state.event_flags = state.event_flags | {self.world.data["event_constants"][event]}
        self.assertIsNone(build_location_guidance(state, RunHistory(), world=self.world).progression_objective)

    def test_hall_of_fame_count_survives_elite_event_reset(self) -> None:
        state = deepcopy(self.state)
        state.badges = 0xFF
        state.earned_badges = ["Boulder", "Cascade", "Thunder", "Rainbow", "Soul", "Marsh", "Volcano", "Earth"]
        state.event_flags = frozenset()
        state.hall_of_fame_team_count = 1
        guidance = build_location_guidance(state, RunHistory(), world=self.world)
        self.assertIsNone(guidance.progression_objective)
        self.assertNotIn("level_cap_exceeded", {item.code for item in guidance.notifications})


class CompletedOnlineSaveGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.state = parse_save_bytes(
            COMPLETED_ONLINE_FIXTURE.read_bytes(), expected_version=GameVersion.BLUE
        )
        cls.world = Gen1WorldDatabase()

    def test_real_completed_save_has_no_mandatory_boss_remaining(self) -> None:
        guidance = build_location_guidance(self.state, RunHistory(), world=self.world)
        self.assertIsNone(guidance.progression_objective)
        self.assertIsNone(guidance.next_trainer)
        self.assertEqual(
            len(self.world.defeated_trainer_ids(self.state, GameVersion.BLUE)), 329
        )

    def test_real_completed_save_item_flags_are_fully_decodable(self) -> None:
        map_ids = {
            item["map_id"] for item in self.world.data["items"]
            if item["version"] in (GameVersion.BLUE.value, "both")
        }
        items = tuple(
            item
            for map_id in map_ids
            for item in self.world.items_for_map(map_id, GameVersion.BLUE, state=self.state)
        )
        self.assertEqual(len(items), 158)
        self.assertEqual(sum(item["collected"] is True for item in items), 107)
        self.assertEqual(sum(item["collected"] is False for item in items), 51)
        self.assertTrue(all(item["collected"] is not None for item in items))


class EncounterHistoryPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = FileSnapshotRepository(self.temporary.name)
        self.profile = RunProfile("sitanshu-blue", "Sitanshu", GameVersion.BLUE)
        self.repository.register_profile(self.profile)

    def test_encounter_state_transitions_are_append_only_and_persistent(self) -> None:
        self.repository.append_encounter_event(
            self.profile.run_id,
            EncounterRecord("route_2", EncounterStatus.ENCOUNTERED, species_id=0x24, method="grass", level=3),
            recorded_at=datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc),
        )
        self.repository.append_encounter_event(
            self.profile.run_id,
            EncounterRecord("route_2", EncounterStatus.CAUGHT, nickname="Birb"),
            recorded_at=datetime(2026, 8, 14, 10, 1, tzinfo=timezone.utc),
        )
        record = self.repository.get_run_history(self.profile.run_id).encounter_for_area("route_2")
        self.assertEqual((record.status, record.species_id, record.nickname), (EncounterStatus.CAUGHT, 0x24, "Birb"))
        directory = Path(self.temporary.name) / "runs" / self.profile.run_id / "history" / "encounters"
        self.assertEqual(len(list(directory.glob("*.json"))), 2)
        with self.assertRaises(ValueError):
            self.repository.append_encounter_event(
                self.profile.run_id,
                EncounterRecord("route_2", EncounterStatus.CAUGHT, species_id=0x24, nickname="Birb", method="grass", level=3),
            )

    def test_latest_snapshot_guidance_uses_persisted_history(self) -> None:
        self.repository.upload_save(self.profile, FIXTURE.read_bytes())
        self.repository.append_encounter_event(
            self.profile.run_id,
            EncounterRecord("route_2", EncounterStatus.CAUGHT, species_id=0x24, nickname="Birb", method="grass", level=3),
        )
        guidance = self.repository.get_latest_guidance(self.profile.run_id)
        route_2 = next(area for area in guidance.nearby_areas if area.area_id == "route_2")
        self.assertFalse(route_2.encounter_available)
        self.assertEqual(guidance.current_location["display_name"], "Pewter City")
        summary = self.repository.list_latest_progress()[0]
        self.assertEqual(summary["nuzlocke_history_status"], "tracked")
        self.assertEqual(summary["encounters"][0]["area_id"], "route_2")


if __name__ == "__main__":
    unittest.main()
