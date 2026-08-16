# Container-level facts about the Gen I save file

TOTAL_SAVE_SIZE = 0x8000  # 32,768 bytes

BANK_SIZE = 0x2000        # 8,192 bytes

BANK_OFFSETS = {
    0: 0x0000,
    1: 0x2000,
    2: 0x4000,
    3: 0x6000,
}

# Banks 2 and 3 each contain six 0x462-byte PC boxes, followed by one
# checksum over all six boxes and six per-box checksums.
STORED_BOXES_PER_BANK = 6
STORED_BOX_SIZE = 0x462
STORED_BOX_BANK_STARTS = (0x4000, 0x6000)
STORED_BOX_DATA_SIZE = STORED_BOXES_PER_BANK * STORED_BOX_SIZE
STORED_BOX_ALL_CHECKSUM_RELATIVE = STORED_BOX_DATA_SIZE
STORED_BOX_INDIVIDUAL_CHECKSUMS_RELATIVE = STORED_BOX_DATA_SIZE + 1
