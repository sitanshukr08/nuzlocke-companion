import unittest

from gen1_save_parser.layout.gen1_items import ITEMS, get_item_data


class ItemRegistryTests(unittest.TestCase):
    def test_canonical_standard_hm_and_tm_names(self) -> None:
        self.assertEqual(get_item_data(0x05).display_name, "Town Map")
        self.assertEqual(get_item_data(0x04).stable_id, "poke_ball")
        self.assertEqual(get_item_data(0xC4).display_name, "HM01 (Cut)")
        self.assertEqual(get_item_data(0xFA).display_name, "TM50 (Substitute)")
        self.assertEqual(len(ITEMS), 138)

    def test_unknown_item_is_preserved_and_labeled(self) -> None:
        item = get_item_data(0xFE)
        self.assertEqual(item.item_id, 0xFE)
        self.assertEqual(item.display_name, "Unknown item 0xFE")


if __name__ == "__main__":
    unittest.main()
