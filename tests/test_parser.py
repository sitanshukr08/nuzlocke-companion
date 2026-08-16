import hashlib
import unittest
from pathlib import Path

from gen1_save_parser import GameVersion, parse_save_bytes, validate_save_bytes
from gen1_save_parser.checksum import calculate_checksum, calculate_main_checksum
from gen1_save_parser.layout.gen1_banks import (
    STORED_BOX_ALL_CHECKSUM_RELATIVE,
    STORED_BOX_BANK_STARTS,
    STORED_BOX_INDIVIDUAL_CHECKSUMS_RELATIVE,
    STORED_BOX_SIZE,
    STORED_BOXES_PER_BANK,
)
from gen1_save_parser.layout.gen1_main_data import (
    BOXES_INITIALIZED_MASK,
    BAG_ITEMS,
    CURRENT_BOX_NUMBER,
    MAIN_DATA_CHECKSUM,
    PARTY_DATA_START,
    PLAYER_X,
    PLAYER_NAME,
    PLAYER_NAME_SIZE,
    MONEY,
)
from gen1_save_parser.layout.gen1_party import (
    FIELD_ATTACK,
    FIELD_CURRENT_HP,
    FIELD_EXP,
    FIELD_MAX_HP,
    FIELD_MOVES,
    FIELD_PP,
    FIELD_SPECIES,
    FIELD_STATUS,
    FIELD_TYPE1,
    PARTY_COUNT_OFFSET,
    POKEMON_DATA_OFFSET,
    SPECIES_LIST_OFFSET,
)
from gen1_save_parser.layout.gen1_species_index import SPECIES_INDEX, get_species_name
from gen1_save_parser.layout.gen1_maps import (
    MAPS,
    POKERED_COMMIT,
    POKERED_MAP_CONSTANTS_SHA256,
    get_map,
)
from gen1_save_parser.models import ParseStatus, StorageBoxStatus
from gen1_save_parser.reader import SaveReader


FIXTURE = Path(__file__).parent / "fixtures" / "pokemon_blue.sav"
COMPLETED_ONLINE_FIXTURE = Path(__file__).parent / "fixtures" / "pokemon_blue_completed_online.sav"


def with_valid_main_checksum(data: bytearray) -> bytes:
    data[MAIN_DATA_CHECKSUM] = calculate_main_checksum(data)
    return bytes(data)


def diagnostic_codes(data: bytes) -> set[str]:
    return {diagnostic.code for diagnostic in validate_save_bytes(data).diagnostics}


def initialize_empty_storage_banks(data: bytearray) -> bytes:
    for bank_start in STORED_BOX_BANK_STARTS:
        for box_index in range(STORED_BOXES_PER_BANK):
            box_start = bank_start + box_index * STORED_BOX_SIZE
            data[box_start] = 0
            data[box_start + 1] = 0xFF
            checksum = calculate_checksum(data[box_start:box_start + STORED_BOX_SIZE])
            data[bank_start + STORED_BOX_INDIVIDUAL_CHECKSUMS_RELATIVE + box_index] = checksum
        data[bank_start + STORED_BOX_ALL_CHECKSUM_RELATIVE] = calculate_checksum(
            data[bank_start:bank_start + STORED_BOXES_PER_BANK * STORED_BOX_SIZE]
        )
    data[CURRENT_BOX_NUMBER] = BOXES_INITIALIZED_MASK
    return with_valid_main_checksum(data)


class GoldenBlueSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = FIXTURE.read_bytes()
        cls.state = parse_save_bytes(cls.data)

    def test_golden_save_is_valid(self) -> None:
        self.assertEqual(self.state.status, ParseStatus.VALID)
        self.assertTrue(self.state.is_valid)
        self.assertEqual(self.state.validation_errors, [])

    def test_golden_top_level_state(self) -> None:
        self.assertEqual(self.state.player_name, "FLAMER")
        self.assertEqual(self.state.player_id, 36591)
        self.assertEqual(self.state.badges, 0)
        self.assertEqual(self.state.current_map_id, 2)
        self.assertEqual(self.state.location_id, "pewter_city")
        self.assertEqual(self.state.location_name, "Pewter City")
        self.assertEqual(len(self.state.party), 3)
        self.assertEqual(len(self.state.current_box), 0)

    def test_golden_main_state(self) -> None:
        self.assertEqual(self.state.rival_name, "JOB")
        self.assertEqual(self.state.money, 895)
        self.assertEqual(
            [(item.item_id, item.quantity) for item in self.state.bag_items],
            [(0x05, 1), (0x04, 4), (0x14, 6), (0x0B, 1)],
        )
        self.assertEqual(self.state.pc_items, [])
        self.assertEqual(self.state.pokedex_owned, [4, 10, 11, 12, 29])
        self.assertEqual(self.state.pokedex_seen, [4, 7, 10, 11, 12, 13, 14, 16, 19, 29])
        self.assertEqual(self.state.earned_badges, [])

    def test_version_is_declared_not_invented_from_save(self) -> None:
        self.assertIsNone(self.state.game_version)
        declared = parse_save_bytes(self.data, expected_version=GameVersion.BLUE)
        self.assertEqual(declared.game_version, GameVersion.BLUE)
        self.assertEqual(declared.game_version_source, "run_configuration")
        with self.assertRaises(TypeError):
            parse_save_bytes(self.data, expected_version="blue")

    def test_uninitialized_storage_is_not_reported_as_empty(self) -> None:
        self.assertFalse(self.state.boxes_initialized)
        self.assertEqual(self.state.current_box_index, 0)
        self.assertEqual(len(self.state.pc_boxes), 12)
        self.assertEqual(self.state.pc_boxes[0].status, StorageBoxStatus.CURRENT_CACHE)
        self.assertTrue(all(
            box.status is StorageBoxStatus.UNINITIALIZED
            for box in self.state.pc_boxes[1:]
        ))

    def test_golden_party(self) -> None:
        expected = [
            ("Nidoran♀", "Potion", 9, 29, 29),
            ("Butterfree", "Keeda", 11, 36, 36),
            ("Charmander", "RealFlamer", 10, 31, 31),
        ]
        actual = [
            (get_species_name(mon.species_id), mon.nickname, mon.level, mon.current_hp, mon.max_hp)
            for mon in self.state.party
        ]
        self.assertEqual(actual, expected)

    def test_golden_party_has_normalized_battle_fields(self) -> None:
        nidoran, butterfree, charmander = self.state.party
        self.assertEqual(nidoran.type_names, ["Poison", "Poison"])
        self.assertEqual(
            [(move.display_name, move.current_pp, move.maximum_pp) for move in nidoran.move_details],
            [("Growl", 40, 40), ("Tackle", 35, 35), ("Scratch", 35, 35)],
        )
        self.assertEqual(butterfree.type_names, ["Bug", "Flying"])
        self.assertEqual(butterfree.moves, [33, 81, 0, 0])
        self.assertEqual(
            [(move.display_name, move.current_pp) for move in butterfree.move_details],
            [("Tackle", 35), ("String Shot", 40)],
        )
        self.assertEqual(charmander.type_names, ["Fire", "Fire"])
        self.assertEqual(charmander.experience_to_next_level, 170)
        self.assertEqual(nidoran.status_conditions, [])

    def test_important_fields_have_source_offsets(self) -> None:
        self.assertEqual(self.state.provenance["party"].offset, PARTY_DATA_START)
        for mon in self.state.party:
            self.assertIn("species_id", mon.provenance)
            self.assertIn("level", mon.provenance)
            self.assertIn("nickname", mon.provenance)


class CompletedOnlineBlueSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = COMPLETED_ONLINE_FIXTURE.read_bytes()
        cls.state = parse_save_bytes(cls.data, expected_version=GameVersion.BLUE)

    def test_fixture_identity_and_strict_validation(self) -> None:
        self.assertEqual(len(self.data), 32768)
        self.assertEqual(
            hashlib.sha256(self.data).hexdigest(),
            "455b9f0e7a6f6831fad130421381723b1d38edcabfd94b58e0d0f8c0605d602d",
        )
        self.assertEqual(self.state.status, ParseStatus.VALID)
        self.assertEqual(self.state.diagnostics, [])

    def test_completed_game_state(self) -> None:
        self.assertEqual((self.state.player_name, self.state.player_id), ("MattiaPK", 15053))
        self.assertEqual((self.state.rival_name, self.state.location_id), ("ROSSO", "pallet_town"))
        self.assertEqual((self.state.player_x, self.state.player_y), (5, 6))
        self.assertEqual(self.state.badges, 0xFF)
        self.assertEqual(len(self.state.earned_badges), 8)
        self.assertEqual(self.state.hall_of_fame_team_count, 1)
        self.assertEqual((len(self.state.pokedex_owned), len(self.state.pokedex_seen)), (151, 151))

    def test_level_100_party_and_current_box_cache(self) -> None:
        self.assertEqual(
            [member.nickname for member in self.state.party],
            ["BLASTOISE", "FEAROW", "NINETALES", "MACHAMP", "EXEGGUTOR", "RHYDON"],
        )
        self.assertTrue(all(member.level == 100 for member in self.state.party))
        self.assertFalse(self.state.boxes_initialized)
        self.assertEqual(len(self.state.pc_boxes[0].members), 20)
        self.assertTrue(all(
            box.status is StorageBoxStatus.UNINITIALIZED for box in self.state.pc_boxes[1:]
        ))


class CorruptionValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original = FIXTURE.read_bytes()

    def test_rejects_wrong_file_size(self) -> None:
        result = validate_save_bytes(self.original[:-1])
        self.assertEqual(result.status, ParseStatus.INVALID)
        self.assertIn("invalid_file_size", diagnostic_codes(self.original[:-1]))

    def test_rejects_checksum_mismatch(self) -> None:
        damaged = bytearray(self.original)
        damaged[0x2598] ^= 0x01
        self.assertIn("main_checksum_mismatch", diagnostic_codes(bytes(damaged)))

    def test_rejects_unterminated_player_name(self) -> None:
        damaged = bytearray(self.original)
        damaged[PLAYER_NAME:PLAYER_NAME + PLAYER_NAME_SIZE] = bytes([0x80] * PLAYER_NAME_SIZE)
        data = with_valid_main_checksum(damaged)
        self.assertIn("unterminated_string", diagnostic_codes(data))

    def test_rejects_unknown_player_name_character(self) -> None:
        damaged = bytearray(self.original)
        damaged[PLAYER_NAME] = 0x01
        data = with_valid_main_checksum(damaged)
        self.assertIn("unknown_string_character", diagnostic_codes(data))

    def test_rejects_empty_player_name(self) -> None:
        damaged = bytearray(self.original)
        damaged[PLAYER_NAME] = 0x50
        data = with_valid_main_checksum(damaged)
        self.assertIn("empty_string", diagnostic_codes(data))

    def test_rejects_invalid_money_bcd(self) -> None:
        damaged = bytearray(self.original)
        damaged[MONEY] = 0xFA
        data = with_valid_main_checksum(damaged)
        self.assertIn("invalid_bcd_digit", diagnostic_codes(data))

    def test_rejects_broken_bag_terminator(self) -> None:
        damaged = bytearray(self.original)
        count = damaged[BAG_ITEMS]
        damaged[BAG_ITEMS + 1 + count * 2] = 0
        data = with_valid_main_checksum(damaged)
        self.assertIn("invalid_bag_items_terminator", diagnostic_codes(data))

    def test_nonstandard_item_is_warning_not_silent_fact(self) -> None:
        damaged = bytearray(self.original)
        damaged[BAG_ITEMS + 1] = 0x54
        data = with_valid_main_checksum(damaged)
        state = parse_save_bytes(data)
        self.assertTrue(state.is_valid)
        self.assertEqual(state.status, ParseStatus.VALID_WITH_WARNINGS)
        self.assertIn("unknown_item_id", {item.code for item in state.diagnostics})

    def test_rejects_party_count_above_six(self) -> None:
        damaged = bytearray(self.original)
        damaged[PARTY_DATA_START + PARTY_COUNT_OFFSET] = 7
        data = with_valid_main_checksum(damaged)
        self.assertIn("invalid_party_count", diagnostic_codes(data))

    def test_rejects_missing_species_list_terminator(self) -> None:
        damaged = bytearray(self.original)
        count = damaged[PARTY_DATA_START + PARTY_COUNT_OFFSET]
        damaged[PARTY_DATA_START + SPECIES_LIST_OFFSET + count] = 0
        data = with_valid_main_checksum(damaged)
        self.assertIn("invalid_party_species_terminator", diagnostic_codes(data))

    def test_rejects_species_list_structure_mismatch(self) -> None:
        damaged = bytearray(self.original)
        damaged[PARTY_DATA_START + SPECIES_LIST_OFFSET] = 0x54
        data = with_valid_main_checksum(damaged)
        self.assertIn("party_species_mismatch", diagnostic_codes(data))

    def test_rejects_missingno_as_owned_species(self) -> None:
        damaged = bytearray(self.original)
        damaged[PARTY_DATA_START + SPECIES_LIST_OFFSET] = 0x1F
        damaged[PARTY_DATA_START + POKEMON_DATA_OFFSET + FIELD_SPECIES] = 0x1F
        data = with_valid_main_checksum(damaged)
        self.assertIn("invalid_party_species", diagnostic_codes(data))

    def test_rejects_current_hp_above_max_hp(self) -> None:
        damaged = bytearray(self.original)
        struct = PARTY_DATA_START + POKEMON_DATA_OFFSET
        max_hp = int.from_bytes(damaged[struct + FIELD_MAX_HP:struct + FIELD_MAX_HP + 2], "big")
        damaged[struct + FIELD_CURRENT_HP:struct + FIELD_CURRENT_HP + 2] = (max_hp + 1).to_bytes(2, "big")
        data = with_valid_main_checksum(damaged)
        self.assertIn("invalid_party_hp", diagnostic_codes(data))
        state = parse_save_bytes(data)
        self.assertFalse(state.is_valid)
        self.assertEqual(state.status, ParseStatus.INVALID)
        self.assertEqual(state.party, [])

    def test_rejects_player_coordinates_outside_current_map(self) -> None:
        damaged = bytearray(self.original)
        damaged[PLAYER_X] = 40  # Pewter City is 40 tiles wide: valid x is 0..39.
        self.assertIn("player_coordinates_out_of_bounds", diagnostic_codes(with_valid_main_checksum(damaged)))

    def test_rejects_species_type_mismatch(self) -> None:
        damaged = bytearray(self.original)
        struct = PARTY_DATA_START + POKEMON_DATA_OFFSET
        damaged[struct + FIELD_TYPE1] = 0
        self.assertIn("pokemon_type_mismatch", diagnostic_codes(with_valid_main_checksum(damaged)))

    def test_rejects_invalid_move_id(self) -> None:
        damaged = bytearray(self.original)
        struct = PARTY_DATA_START + POKEMON_DATA_OFFSET
        damaged[struct + FIELD_MOVES] = 0xA6
        self.assertIn("invalid_move_id", diagnostic_codes(with_valid_main_checksum(damaged)))

    def test_rejects_move_after_empty_slot(self) -> None:
        damaged = bytearray(self.original)
        struct = PARTY_DATA_START + POKEMON_DATA_OFFSET
        damaged[struct + FIELD_MOVES + 1] = 0
        damaged[struct + FIELD_PP + 1] = 0
        self.assertIn("move_after_empty_slot", diagnostic_codes(with_valid_main_checksum(damaged)))

    def test_rejects_pp_for_empty_move(self) -> None:
        damaged = bytearray(self.original)
        struct = PARTY_DATA_START + POKEMON_DATA_OFFSET
        damaged[struct + FIELD_PP + 3] = 1
        self.assertIn("pp_for_empty_move", diagnostic_codes(with_valid_main_checksum(damaged)))

    def test_rejects_pp_above_move_maximum(self) -> None:
        damaged = bytearray(self.original)
        struct = PARTY_DATA_START + POKEMON_DATA_OFFSET
        damaged[struct + FIELD_PP] = 63
        self.assertIn("pp_exceeds_maximum", diagnostic_codes(with_valid_main_checksum(damaged)))

    def test_rejects_reserved_and_conflicting_status(self) -> None:
        damaged = bytearray(self.original)
        struct = PARTY_DATA_START + POKEMON_DATA_OFFSET
        damaged[struct + FIELD_STATUS] = 0x89
        codes = diagnostic_codes(with_valid_main_checksum(damaged))
        self.assertIn("invalid_status_bits", codes)
        self.assertIn("conflicting_status_conditions", codes)

    def test_rejects_experience_below_level_minimum(self) -> None:
        damaged = bytearray(self.original)
        struct = PARTY_DATA_START + POKEMON_DATA_OFFSET
        damaged[struct + FIELD_EXP:struct + FIELD_EXP + 3] = (0).to_bytes(3, "big")
        self.assertIn("experience_below_level_minimum", diagnostic_codes(with_valid_main_checksum(damaged)))

    def test_rejects_experience_reaching_next_level(self) -> None:
        damaged = bytearray(self.original)
        struct = PARTY_DATA_START + POKEMON_DATA_OFFSET
        damaged[struct + FIELD_EXP:struct + FIELD_EXP + 3] = (640).to_bytes(3, "big")
        self.assertIn("experience_reaches_next_level", diagnostic_codes(with_valid_main_checksum(damaged)))

    def test_rejects_calculated_party_stat_mismatch(self) -> None:
        damaged = bytearray(self.original)
        struct = PARTY_DATA_START + POKEMON_DATA_OFFSET
        damaged[struct + FIELD_ATTACK + 1] ^= 1
        self.assertIn("calculated_stat_mismatch", diagnostic_codes(with_valid_main_checksum(damaged)))

    def test_initialized_storage_boxes_and_checksums_parse(self) -> None:
        data = initialize_empty_storage_banks(bytearray(self.original))
        state = parse_save_bytes(data)
        self.assertTrue(state.is_valid)
        self.assertTrue(state.boxes_initialized)
        self.assertEqual(len(state.pc_boxes), 12)
        self.assertEqual(state.pc_boxes[0].status, StorageBoxStatus.CURRENT_CACHE)
        self.assertTrue(all(box.members == [] for box in state.pc_boxes))
        self.assertTrue(all(
            box.checksum_verified is True
            for box in state.pc_boxes
        ))

    def test_rejects_initialized_storage_box_checksum_mismatch(self) -> None:
        data = bytearray(initialize_empty_storage_banks(bytearray(self.original)))
        data[STORED_BOX_BANK_STARTS[0] + STORED_BOX_INDIVIDUAL_CHECKSUMS_RELATIVE] ^= 0x01
        self.assertIn("box_checksum_mismatch", diagnostic_codes(bytes(data)))


class SpeciesIndexTests(unittest.TestCase):
    def test_contains_all_151_real_species(self) -> None:
        self.assertEqual(len(SPECIES_INDEX), 151)

    def test_internal_ids_are_not_assumed_to_be_dex_numbers(self) -> None:
        self.assertEqual(get_species_name(0x54), "Pikachu")
        self.assertEqual(get_species_name(0x7D), "Butterfree")
        self.assertEqual(get_species_name(0xB0), "Charmander")


class MapRegistryTests(unittest.TestCase):
    def test_registry_contains_every_red_blue_map(self) -> None:
        self.assertEqual(len(MAPS), 248)
        self.assertEqual(get_map(0x00).stable_id, "pallet_town")
        self.assertEqual(get_map(0xF7).stable_id, "agathas_room")

    def test_registry_has_reproducible_source_provenance(self) -> None:
        self.assertEqual(POKERED_COMMIT, "0cd19d3b877b7dc66d12c7050bed9a7f38154d4b")
        self.assertEqual(
            POKERED_MAP_CONSTANTS_SHA256,
            "4129ef4e6908267e554c0308254f2269f1fb8f75b5c529faad6fd14c92119271",
        )


class SaveReaderBoundaryTests(unittest.TestCase):
    def test_negative_read_size_is_rejected(self) -> None:
        reader = SaveReader(b"abc")
        with self.assertRaises(ValueError):
            reader.read_bytes(1, -1)
        with self.assertRaises(ValueError):
            reader.read_int(1, -1)

    def test_zero_length_read_at_end_is_valid(self) -> None:
        self.assertEqual(SaveReader(b"abc").read_bytes(3, 0), b"")


if __name__ == "__main__":
    unittest.main()
