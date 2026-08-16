import unittest

from gen1_save_parser.layout.gen1_battle_data import (
    MOVES,
    SPECIES_BASE_DATA,
    TYPES,
    POKERED_BATTLE_SOURCES_SHA256,
    POKERED_COMMIT,
    get_move,
    get_species_base_data,
)
from gen1_save_parser.mechanics import (
    calculate_party_stats,
    decode_dvs,
    decode_status,
    experience_for_level,
    maximum_pp,
)


class BattleDataRegistryTests(unittest.TestCase):
    def test_registry_is_complete_and_pinned(self) -> None:
        self.assertEqual(len(TYPES), 16)
        self.assertEqual(len(MOVES), 165)
        self.assertEqual(len(SPECIES_BASE_DATA), 151)
        self.assertEqual(POKERED_COMMIT, "0cd19d3b877b7dc66d12c7050bed9a7f38154d4b")
        self.assertEqual(
            POKERED_BATTLE_SOURCES_SHA256,
            "6281867a7224ca99796dbce014af2f36e38eff1670359c86ee39ed83a764b5fc",
        )

    def test_known_move_and_species_data(self) -> None:
        tackle = get_move(33)
        self.assertEqual((tackle.display_name, tackle.power, tackle.base_pp), ("Tackle", 35, 35))
        charmander = get_species_base_data(0xB0)
        self.assertEqual(charmander.display_name, "Charmander")
        self.assertEqual((charmander.type1_id, charmander.type2_id), (0x14, 0x14))
        self.assertEqual(charmander.growth_rate, "medium_slow")


class MechanicsTests(unittest.TestCase):
    def test_experience_curves(self) -> None:
        self.assertEqual(experience_for_level("medium_fast", 10), 1000)
        self.assertEqual(experience_for_level("medium_slow", 10), 560)
        self.assertEqual(experience_for_level("fast", 10), 800)
        self.assertEqual(experience_for_level("slow", 10), 1250)

    def test_pp_ups_and_status_decode(self) -> None:
        self.assertEqual(maximum_pp(get_move(33), 3), 56)
        self.assertEqual(maximum_pp(get_move(45), 3), 61)
        self.assertEqual(decode_status(0x00), [])
        self.assertEqual(decode_status(0x09), ["sleep", "poison"])

    def test_dvs_and_party_stat_calculation(self) -> None:
        self.assertEqual(
            decode_dvs(0x1234),
            {"hp": 10, "attack": 1, "defense": 2, "speed": 3, "special": 4},
        )
        charmander = get_species_base_data(0xB0)
        stats = calculate_party_stats(charmander, 0, [0, 0, 0, 0, 0], 10)
        self.assertEqual(stats, {"hp": 27, "attack": 15, "defense": 13, "speed": 18, "special": 15})

    def test_stat_experience_uses_the_games_ceiling_square_root(self) -> None:
        charmander = get_species_base_data(0xB0)
        stats = calculate_party_stats(charmander, 0, [10, 10, 10, 10, 10], 100)
        self.assertEqual(
            stats,
            {"hp": 189, "attack": 110, "defense": 92, "speed": 136, "special": 106},
        )


if __name__ == "__main__":
    unittest.main()
