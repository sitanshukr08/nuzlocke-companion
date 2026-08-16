from .layout.gen1_main_data import CHECKSUM_START, CHECKSUM_END, MAIN_DATA_CHECKSUM


def calculate_checksum(data: bytes) -> int:
    """Calculate the complemented 8-bit additive checksum used by Gen I."""
    return (~(sum(data) & 0xFF)) & 0xFF

def calculate_main_checksum(save_data: bytes) -> int:
    """
    Calculate the Bank 1 main data checksum.
    The algorithm is:
    1. Start an 8-bit accumulator at 0
    2. Add every byte from CHECKSUM_START to CHECKSUM_END - 1 to the accumulator (mod 256)
    3. Bitwise-NOT (invert) the final value
    """
    return calculate_checksum(save_data[CHECKSUM_START:CHECKSUM_END])

def verify_main_checksum(save_data: bytes) -> bool:
    """
    Verify if the calculated checksum matches the stored checksum.
    """
    if len(save_data) <= MAIN_DATA_CHECKSUM:
        return False
    expected = save_data[MAIN_DATA_CHECKSUM]
    actual = calculate_main_checksum(save_data)
    return expected == actual
