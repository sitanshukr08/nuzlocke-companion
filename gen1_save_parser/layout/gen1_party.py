# Party Data Structure (offset 0x2F2C)
# 404 bytes total

PARTY_COUNT_OFFSET = 0x00
SPECIES_LIST_OFFSET = 0x01
SPECIES_LIST_SIZE = 7

# Six 44-byte Pokemon structures, back to back
POKEMON_DATA_OFFSET = 0x08
POKEMON_DATA_STRUCT_SIZE = 44
MAX_PARTY_SIZE = 6

# Original Trainer names (11 bytes each * 6)
OT_NAMES_OFFSET = 0x110
OT_NAMES_SIZE = 11 * 6

# Nicknames (11 bytes each * 6)
NICKNAMES_OFFSET = 0x152
NICKNAMES_SIZE = 11 * 6

# 44-byte struct sub-offsets (relative to start of individual Pokemon struct)
FIELD_SPECIES = 0x00
FIELD_CURRENT_HP = 0x01
FIELD_LEVEL = 0x03 # Boxed-form level byte retained inside the party structure
FIELD_STATUS = 0x04
FIELD_TYPE1 = 0x05
FIELD_TYPE2 = 0x06
FIELD_CATCH_RATE = 0x07
FIELD_MOVES = 0x08 # 4 bytes
FIELD_OT_ID = 0x0C
FIELD_EXP = 0x0E # 3 bytes
FIELD_STAT_EXP = 0x11 # 10 bytes
FIELD_DVS = 0x1B # 2 bytes
FIELD_PP = 0x1D # 4 bytes
FIELD_LEVEL_2 = 0x21 # Authoritative current level for a party Pokemon
FIELD_MAX_HP = 0x22
FIELD_ATTACK = 0x24
FIELD_DEFENSE = 0x26
FIELD_SPEED = 0x28
FIELD_SPECIAL = 0x2A
