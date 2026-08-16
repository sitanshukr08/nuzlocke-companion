import random
import unittest
from pathlib import Path

from gen1_save_parser import validate_save_bytes
from gen1_save_parser.layout.gen1_main_data import CHECKSUM_END, CHECKSUM_START
from gen1_save_parser.models import ParseStatus


FIXTURE = Path(__file__).parent / "fixtures" / "pokemon_blue.sav"


class ParserRobustnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = FIXTURE.read_bytes()

    def test_every_single_byte_mutation_in_main_region_breaks_checksum(self) -> None:
        for offset in range(CHECKSUM_START, CHECKSUM_END):
            with self.subTest(offset=offset):
                damaged = bytearray(self.fixture)
                damaged[offset] ^= 0x01
                result = validate_save_bytes(bytes(damaged))
                self.assertEqual(result.status, ParseStatus.INVALID)
                self.assertIn(
                    "main_checksum_mismatch",
                    {diagnostic.code for diagnostic in result.diagnostics},
                )

    def test_random_full_size_inputs_never_crash_or_validate(self) -> None:
        generator = random.Random(0xC0DE)
        for case in range(250):
            with self.subTest(case=case):
                result = validate_save_bytes(generator.randbytes(32768))
                self.assertEqual(result.status, ParseStatus.INVALID)

    def test_boundary_file_sizes_are_structured_invalid_results(self) -> None:
        for size in (0, 1, 32767, 32769, 65536):
            with self.subTest(size=size):
                result = validate_save_bytes(bytes(size))
                self.assertEqual(result.status, ParseStatus.INVALID)
                self.assertEqual(result.diagnostics[0].code, "invalid_file_size")


if __name__ == "__main__":
    unittest.main()
