from dataclasses import dataclass

from .checksum import calculate_checksum, verify_main_checksum
from .layout.gen1_banks import (
    STORED_BOX_ALL_CHECKSUM_RELATIVE,
    STORED_BOX_BANK_STARTS,
    STORED_BOX_DATA_SIZE,
    STORED_BOX_INDIVIDUAL_CHECKSUMS_RELATIVE,
    STORED_BOX_SIZE,
    STORED_BOXES_PER_BANK,
    TOTAL_SAVE_SIZE,
)
from .layout.gen1_box import (
    BOX_COUNT_OFFSET,
    BOX_POKEMON_DATA_OFFSET,
    BOX_POKEMON_DATA_STRUCT_SIZE,
    BOX_SPECIES_LIST_OFFSET,
    BOX_NICKNAMES_OFFSET,
    BOX_OT_NAMES_OFFSET,
    FIELD_LEVEL as BOX_FIELD_LEVEL,
    MAX_BOX_SIZE,
)
from .layout.gen1_battle_data import get_move, get_species_base_data
from .layout.gen1_charmap import CHARMAP
from .layout.gen1_main_data import (
    BOXES_INITIALIZED_MASK,
    BOX_NUMBER_MASK,
    CURRENT_BOX_NUMBER,
    CURRENT_BOX_START,
    CURRENT_MAP_ID,
    PLAYER_X,
    PLAYER_Y,
    BAG_ITEMS,
    MAX_BAG_ITEMS,
    MAX_PC_ITEMS,
    MONEY,
    MONEY_SIZE,
    PARTY_DATA_START,
    PC_ITEMS,
    PLAYER_NAME,
    PLAYER_NAME_SIZE,
    RIVAL_NAME,
    RIVAL_NAME_SIZE,
)
from .layout.gen1_party import (
    FIELD_ATTACK,
    FIELD_DEFENSE,
    FIELD_DVS,
    FIELD_EXP,
    FIELD_LEVEL_2,
    FIELD_MAX_HP,
    FIELD_CURRENT_HP,
    FIELD_MOVES,
    FIELD_PP,
    FIELD_SPECIAL,
    FIELD_SPEED,
    FIELD_STAT_EXP,
    FIELD_STATUS,
    FIELD_TYPE1,
    FIELD_TYPE2,
    MAX_PARTY_SIZE,
    PARTY_COUNT_OFFSET,
    POKEMON_DATA_OFFSET,
    POKEMON_DATA_STRUCT_SIZE,
    SPECIES_LIST_OFFSET,
    NICKNAMES_OFFSET,
    OT_NAMES_OFFSET,
)
from .layout.gen1_species_index import is_valid_species_id
from .layout.gen1_maps import get_map
from .mechanics import calculate_party_stats, decode_status, experience_for_level, maximum_pp
from .models import Diagnostic, DiagnosticSeverity, ParseStatus
from .reader import SaveReader

LIST_TERMINATOR = 0xFF
STRING_TERMINATOR = 0x50
NAME_LENGTH = 11


@dataclass(frozen=True)
class ValidationResult:
    status: ParseStatus
    diagnostics: tuple[Diagnostic, ...]

    @property
    def can_parse(self) -> bool:
        return self.status in (ParseStatus.VALID, ParseStatus.VALID_WITH_WARNINGS)


def _error(code: str, message: str, offset: int | None = None, **details: object) -> Diagnostic:
    return Diagnostic(code, DiagnosticSeverity.ERROR, message, offset, details)


def _warning(code: str, message: str, offset: int | None = None, **details: object) -> Diagnostic:
    return Diagnostic(code, DiagnosticSeverity.WARNING, message, offset, details)


def _validate_pokemon_semantics(
    reader: SaveReader,
    *,
    label: str,
    index: int,
    struct_address: int,
    level: int,
    has_party_stats: bool,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    species_id = reader.read_byte(struct_address)
    species = get_species_base_data(species_id)
    if species is None:
        return diagnostics

    stored_types = (
        reader.read_byte(struct_address + FIELD_TYPE1),
        reader.read_byte(struct_address + FIELD_TYPE2),
    )
    expected_types = (species.type1_id, species.type2_id)
    if stored_types != expected_types:
        diagnostics.append(_error(
            "pokemon_type_mismatch",
            f"{label.title()} member {index} types do not match {species.display_name} base data",
            struct_address + FIELD_TYPE1,
            index=index,
            species_id=species_id,
            stored=list(stored_types),
            expected=list(expected_types),
        ))

    status_address = struct_address + FIELD_STATUS
    status = reader.read_byte(status_address)
    if status & 0x80:
        diagnostics.append(_error(
            "invalid_status_bits",
            f"{label.title()} member {index} uses reserved status bit 7",
            status_address,
            index=index,
            status=status,
        ))
    conditions = decode_status(status)
    if len(conditions) > 1:
        diagnostics.append(_error(
            "conflicting_status_conditions",
            f"{label.title()} member {index} has mutually exclusive status conditions",
            status_address,
            index=index,
            conditions=conditions,
        ))

    found_empty_move = False
    for slot in range(4):
        move_address = struct_address + FIELD_MOVES + slot
        pp_address = struct_address + FIELD_PP + slot
        move_id = reader.read_byte(move_address)
        pp_byte = reader.read_byte(pp_address)
        if move_id == 0:
            found_empty_move = True
            if pp_byte != 0:
                diagnostics.append(_error(
                    "pp_for_empty_move",
                    f"{label.title()} member {index} has PP in empty move slot {slot}",
                    pp_address,
                    index=index,
                    slot=slot,
                    pp_byte=pp_byte,
                ))
            continue
        if found_empty_move:
            diagnostics.append(_error(
                "move_after_empty_slot",
                f"{label.title()} member {index} has a move after an empty slot",
                move_address,
                index=index,
                slot=slot,
                move_id=move_id,
            ))
        move = get_move(move_id)
        if move is None:
            diagnostics.append(_error(
                "invalid_move_id",
                f"{label.title()} member {index} has invalid Gen I move ID {move_id:#04x}",
                move_address,
                index=index,
                slot=slot,
                move_id=move_id,
            ))
            continue
        pp_ups = pp_byte >> 6
        current_pp = pp_byte & 0x3F
        allowed_pp = maximum_pp(move, pp_ups)
        if current_pp > allowed_pp:
            diagnostics.append(_error(
                "pp_exceeds_maximum",
                f"{label.title()} member {index} move slot {slot} has {current_pp} PP; maximum is {allowed_pp}",
                pp_address,
                index=index,
                slot=slot,
                move_id=move_id,
                current_pp=current_pp,
                maximum_pp=allowed_pp,
                pp_ups=pp_ups,
            ))

    experience_address = struct_address + FIELD_EXP
    experience = reader.read_int(experience_address, 3)
    minimum = experience_for_level(species.growth_rate, level)
    if experience < minimum:
        diagnostics.append(_error(
            "experience_below_level_minimum",
            f"{label.title()} member {index} has too little experience for level {level}",
            experience_address,
            index=index,
            experience=experience,
            minimum=minimum,
        ))
    elif level < 100:
        next_level = experience_for_level(species.growth_rate, level + 1)
        if experience >= next_level:
            diagnostics.append(_error(
                "experience_reaches_next_level",
                f"{label.title()} member {index} experience reaches level {level + 1}",
                experience_address,
                index=index,
                experience=experience,
                next_level_threshold=next_level,
            ))

    if has_party_stats:
        stat_exp = [reader.read_int(struct_address + FIELD_STAT_EXP + slot * 2, 2) for slot in range(5)]
        dvs = reader.read_int(struct_address + FIELD_DVS, 2)
        calculated = calculate_party_stats(species, dvs, stat_exp, level)
        stored = {
            "hp": reader.read_int(struct_address + FIELD_MAX_HP, 2),
            "attack": reader.read_int(struct_address + FIELD_ATTACK, 2),
            "defense": reader.read_int(struct_address + FIELD_DEFENSE, 2),
            "speed": reader.read_int(struct_address + FIELD_SPEED, 2),
            "special": reader.read_int(struct_address + FIELD_SPECIAL, 2),
        }
        if stored != calculated:
            diagnostics.append(_error(
                "calculated_stat_mismatch",
                f"{label.title()} member {index} calculated stats do not match stored stats",
                struct_address + FIELD_MAX_HP,
                index=index,
                stored=stored,
                expected=calculated,
            ))

    return diagnostics


def _validate_collection(
    reader: SaveReader,
    *,
    label: str,
    start: int,
    count_offset: int,
    species_list_offset: int,
    struct_offset: int,
    struct_size: int,
    maximum: int,
    level_offset: int,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    count_address = start + count_offset
    count = reader.read_byte(count_address)
    if count > maximum:
        return [_error(
            f"invalid_{label}_count",
            f"{label.title()} count {count} exceeds maximum {maximum}",
            count_address,
            actual=count,
            maximum=maximum,
        )]

    terminator_address = start + species_list_offset + count
    terminator = reader.read_byte(terminator_address)
    if terminator != LIST_TERMINATOR:
        diagnostics.append(_error(
            f"invalid_{label}_species_terminator",
            f"{label.title()} species list is not terminated after {count} entries",
            terminator_address,
            actual=terminator,
            expected=LIST_TERMINATOR,
        ))

    for index in range(count):
        list_address = start + species_list_offset + index
        struct_address = start + struct_offset + index * struct_size
        listed_species = reader.read_byte(list_address)
        stored_species = reader.read_byte(struct_address)
        if listed_species != stored_species:
            diagnostics.append(_error(
                f"{label}_species_mismatch",
                f"{label.title()} member {index} species list and structure disagree",
                struct_address,
                index=index,
                listed=listed_species,
                stored=stored_species,
            ))
        if not is_valid_species_id(stored_species):
            diagnostics.append(_error(
                f"invalid_{label}_species",
                f"{label.title()} member {index} has invalid Gen I species ID {stored_species:#04x}",
                struct_address,
                index=index,
                species_id=stored_species,
            ))

        level_address = struct_address + level_offset
        level = reader.read_byte(level_address)
        if not 1 <= level <= 100:
            diagnostics.append(_error(
                f"invalid_{label}_level",
                f"{label.title()} member {index} has invalid level {level}",
                level_address,
                index=index,
                level=level,
            ))
        elif is_valid_species_id(stored_species):
            diagnostics.extend(_validate_pokemon_semantics(
                reader,
                label=label,
                index=index,
                struct_address=struct_address,
                level=level,
                has_party_stats=struct_size == POKEMON_DATA_STRUCT_SIZE,
            ))

    return diagnostics


def _validate_string(reader: SaveReader, *, label: str, offset: int, length: int = NAME_LENGTH) -> list[Diagnostic]:
    raw = reader.read_bytes(offset, length)
    try:
        terminator_index = raw.index(STRING_TERMINATOR)
    except ValueError:
        return [_error(
            "unterminated_string",
            f"{label} has no Gen I string terminator within {length} bytes",
            offset,
            field=label,
            length=length,
        )]

    diagnostics: list[Diagnostic] = []
    if terminator_index == 0:
        diagnostics.append(_error(
            "empty_string",
            f"{label} is empty",
            offset,
            field=label,
        ))
    for index, value in enumerate(raw[:terminator_index]):
        if value not in CHARMAP:
            diagnostics.append(_error(
                "unknown_string_character",
                f"{label} contains unmapped character byte {value:#04x}",
                offset + index,
                field=label,
                value=value,
            ))
    return diagnostics


def _validate_collection_strings(
    reader: SaveReader,
    *,
    label: str,
    start: int,
    count_offset: int,
    ot_names_offset: int,
    nicknames_offset: int,
    maximum: int,
) -> list[Diagnostic]:
    count = reader.read_byte(start + count_offset)
    if count > maximum:
        return []
    diagnostics: list[Diagnostic] = []
    for index in range(count):
        diagnostics.extend(_validate_string(
            reader,
            label=f"{label}[{index}].original_trainer_name",
            offset=start + ot_names_offset + index * NAME_LENGTH,
        ))
        diagnostics.extend(_validate_string(
            reader,
            label=f"{label}[{index}].nickname",
            offset=start + nicknames_offset + index * NAME_LENGTH,
        ))
    return diagnostics


def _is_standard_item_id(item_id: int) -> bool:
    normal_item = 0x01 <= item_id <= 0x53 and item_id not in (0x2C, 0x32)
    hm_or_tm = 0xC4 <= item_id <= 0xFA
    return normal_item or hm_or_tm


def _validate_item_list(
    reader: SaveReader,
    *,
    label: str,
    offset: int,
    maximum: int,
) -> list[Diagnostic]:
    count = reader.read_byte(offset)
    if count > maximum:
        return [_error(
            f"invalid_{label}_count",
            f"{label.replace('_', ' ').title()} count {count} exceeds maximum {maximum}",
            offset,
            actual=count,
            maximum=maximum,
        )]
    diagnostics: list[Diagnostic] = []
    for index in range(count):
        entry_offset = offset + 1 + index * 2
        item_id = reader.read_byte(entry_offset)
        quantity = reader.read_byte(entry_offset + 1)
        if not _is_standard_item_id(item_id):
            diagnostics.append(_warning(
                "unknown_item_id",
                f"{label.replace('_', ' ').title()} entry {index} uses nonstandard item ID {item_id:#04x}",
                entry_offset,
                field=label,
                index=index,
                item_id=item_id,
            ))
        if quantity == 0:
            diagnostics.append(_warning(
                "zero_item_quantity",
                f"{label.replace('_', ' ').title()} entry {index} has zero quantity",
                entry_offset + 1,
                field=label,
                index=index,
            ))
    terminator_offset = offset + 1 + count * 2
    terminator = reader.read_byte(terminator_offset)
    if terminator != LIST_TERMINATOR:
        diagnostics.append(_error(
            f"invalid_{label}_terminator",
            f"{label.replace('_', ' ').title()} is not terminated after {count} entries",
            terminator_offset,
            actual=terminator,
            expected=LIST_TERMINATOR,
        ))
    return diagnostics


def _validate_bcd(reader: SaveReader, *, label: str, offset: int, length: int) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for index, value in enumerate(reader.read_bytes(offset, length)):
        if value >> 4 > 9 or value & 0x0F > 9:
            diagnostics.append(_error(
                "invalid_bcd_digit",
                f"{label} contains invalid BCD byte {value:#04x}",
                offset + index,
                field=label,
                value=value,
            ))
    return diagnostics


def validate_save_bytes(data: bytes) -> ValidationResult:
    diagnostics: list[Diagnostic] = []
    if len(data) != TOTAL_SAVE_SIZE:
        diagnostics.append(_error(
            "invalid_file_size",
            f"Expected {TOTAL_SAVE_SIZE} bytes, got {len(data)}",
            expected=TOTAL_SAVE_SIZE,
            actual=len(data),
        ))
        return ValidationResult(ParseStatus.INVALID, tuple(diagnostics))

    if not verify_main_checksum(data):
        diagnostics.append(_error(
            "main_checksum_mismatch",
            "Main save-data checksum does not match",
        ))

    reader = SaveReader(data)
    diagnostics.extend(_validate_string(
        reader,
        label="player_name",
        offset=PLAYER_NAME,
        length=PLAYER_NAME_SIZE,
    ))
    diagnostics.extend(_validate_string(
        reader,
        label="rival_name",
        offset=RIVAL_NAME,
        length=RIVAL_NAME_SIZE,
    ))
    diagnostics.extend(_validate_bcd(
        reader,
        label="money",
        offset=MONEY,
        length=MONEY_SIZE,
    ))
    diagnostics.extend(_validate_item_list(
        reader,
        label="bag_items",
        offset=BAG_ITEMS,
        maximum=MAX_BAG_ITEMS,
    ))
    diagnostics.extend(_validate_item_list(
        reader,
        label="pc_items",
        offset=PC_ITEMS,
        maximum=MAX_PC_ITEMS,
    ))
    diagnostics.extend(_validate_collection(
        reader,
        label="party",
        start=PARTY_DATA_START,
        count_offset=PARTY_COUNT_OFFSET,
        species_list_offset=SPECIES_LIST_OFFSET,
        struct_offset=POKEMON_DATA_OFFSET,
        struct_size=POKEMON_DATA_STRUCT_SIZE,
        maximum=MAX_PARTY_SIZE,
        level_offset=FIELD_LEVEL_2,
    ))
    diagnostics.extend(_validate_collection_strings(
        reader,
        label="party",
        start=PARTY_DATA_START,
        count_offset=PARTY_COUNT_OFFSET,
        ot_names_offset=OT_NAMES_OFFSET,
        nicknames_offset=NICKNAMES_OFFSET,
        maximum=MAX_PARTY_SIZE,
    ))
    diagnostics.extend(_validate_collection(
        reader,
        label="box",
        start=CURRENT_BOX_START,
        count_offset=BOX_COUNT_OFFSET,
        species_list_offset=BOX_SPECIES_LIST_OFFSET,
        struct_offset=BOX_POKEMON_DATA_OFFSET,
        struct_size=BOX_POKEMON_DATA_STRUCT_SIZE,
        maximum=MAX_BOX_SIZE,
        level_offset=BOX_FIELD_LEVEL,
    ))
    diagnostics.extend(_validate_collection_strings(
        reader,
        label="current_box",
        start=CURRENT_BOX_START,
        count_offset=BOX_COUNT_OFFSET,
        ot_names_offset=BOX_OT_NAMES_OFFSET,
        nicknames_offset=BOX_NICKNAMES_OFFSET,
        maximum=MAX_BOX_SIZE,
    ))

    current_box_raw = reader.read_byte(CURRENT_BOX_NUMBER)
    current_box_index = current_box_raw & BOX_NUMBER_MASK
    boxes_initialized = bool(current_box_raw & BOXES_INITIALIZED_MASK)
    if current_box_index >= 12:
        diagnostics.append(_error(
            "invalid_current_box_index",
            f"Current PC box index {current_box_index} is outside 0..11",
            CURRENT_BOX_NUMBER,
            current_box_index=current_box_index,
        ))

    current_map_id = reader.read_byte(CURRENT_MAP_ID)
    current_map = get_map(current_map_id)
    if current_map is None:
        diagnostics.append(_error(
            "invalid_current_map_id",
            f"Current map ID {current_map_id:#04x} is not a Red/Blue map",
            CURRENT_MAP_ID,
            map_id=current_map_id,
        ))
    elif current_map.is_unused:
        diagnostics.append(_warning(
            "unused_current_map_id",
            f"Current map points to unused map {current_map.display_name}",
            CURRENT_MAP_ID,
            map_id=current_map_id,
        ))
    else:
        player_x = reader.read_byte(PLAYER_X)
        player_y = reader.read_byte(PLAYER_Y)
        if player_x >= current_map.width_blocks * 2 or player_y >= current_map.height_blocks * 2:
            diagnostics.append(_error(
                "player_coordinates_out_of_bounds",
                f"Player coordinates ({player_x}, {player_y}) are outside {current_map.display_name}",
                PLAYER_Y,
                player_x=player_x,
                player_y=player_y,
                width_tiles=current_map.width_blocks * 2,
                height_tiles=current_map.height_blocks * 2,
            ))

    # The storage banks contain untouched 0xFF data until the first box switch.
    # Only validate them once the game's initialization flag is set.
    if boxes_initialized:
        for bank_number, bank_start in enumerate(STORED_BOX_BANK_STARTS, start=2):
            bank_data_end = bank_start + STORED_BOX_DATA_SIZE
            expected_all = reader.read_byte(bank_start + STORED_BOX_ALL_CHECKSUM_RELATIVE)
            actual_all = calculate_checksum(data[bank_start:bank_data_end])
            if expected_all != actual_all:
                diagnostics.append(_error(
                    "box_bank_checksum_mismatch",
                    f"PC box bank {bank_number} checksum does not match",
                    bank_start + STORED_BOX_ALL_CHECKSUM_RELATIVE,
                    bank=bank_number,
                    expected=expected_all,
                    actual=actual_all,
                ))

            for bank_box_index in range(STORED_BOXES_PER_BANK):
                absolute_index = (bank_number - 2) * STORED_BOXES_PER_BANK + bank_box_index
                box_start = bank_start + bank_box_index * STORED_BOX_SIZE
                checksum_offset = bank_start + STORED_BOX_INDIVIDUAL_CHECKSUMS_RELATIVE + bank_box_index
                expected = reader.read_byte(checksum_offset)
                actual = calculate_checksum(data[box_start:box_start + STORED_BOX_SIZE])
                if expected != actual:
                    diagnostics.append(_error(
                        "box_checksum_mismatch",
                        f"PC box {absolute_index + 1} checksum does not match",
                        checksum_offset,
                        box_index=absolute_index,
                        expected=expected,
                        actual=actual,
                    ))
                diagnostics.extend(_validate_collection(
                    reader,
                    label=f"pc_box_{absolute_index + 1}",
                    start=box_start,
                    count_offset=BOX_COUNT_OFFSET,
                    species_list_offset=BOX_SPECIES_LIST_OFFSET,
                    struct_offset=BOX_POKEMON_DATA_OFFSET,
                    struct_size=BOX_POKEMON_DATA_STRUCT_SIZE,
                    maximum=MAX_BOX_SIZE,
                    level_offset=BOX_FIELD_LEVEL,
                ))
                diagnostics.extend(_validate_collection_strings(
                    reader,
                    label=f"pc_box_{absolute_index + 1}",
                    start=box_start,
                    count_offset=BOX_COUNT_OFFSET,
                    ot_names_offset=BOX_OT_NAMES_OFFSET,
                    nicknames_offset=BOX_NICKNAMES_OFFSET,
                    maximum=MAX_BOX_SIZE,
                ))

    # Party-only derived stats provide a useful internal consistency check.
    party_count = reader.read_byte(PARTY_DATA_START + PARTY_COUNT_OFFSET)
    if party_count <= MAX_PARTY_SIZE:
        for index in range(party_count):
            struct_address = PARTY_DATA_START + POKEMON_DATA_OFFSET + index * POKEMON_DATA_STRUCT_SIZE
            current_hp = reader.read_int(struct_address + FIELD_CURRENT_HP, 2)
            max_hp = reader.read_int(struct_address + FIELD_MAX_HP, 2)
            if max_hp == 0 or current_hp > max_hp:
                diagnostics.append(_error(
                    "invalid_party_hp",
                    f"Party member {index} has HP {current_hp}/{max_hp}",
                    struct_address + FIELD_CURRENT_HP,
                    index=index,
                    current_hp=current_hp,
                    max_hp=max_hp,
                ))

    has_errors = any(item.severity is DiagnosticSeverity.ERROR for item in diagnostics)
    has_warnings = any(item.severity is DiagnosticSeverity.WARNING for item in diagnostics)
    status = (
        ParseStatus.INVALID if has_errors
        else ParseStatus.VALID_WITH_WARNINGS if has_warnings
        else ParseStatus.VALID
    )
    return ValidationResult(status, tuple(diagnostics))
