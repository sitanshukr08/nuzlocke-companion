from .reader import SaveReader
from .models import (
    Diagnostic, DiagnosticSeverity, FieldProvenance, ParseStatus,
    SaveState, PartyMember, BoxMember, StorageBox, StorageBoxStatus,
    GameVersion, InventoryEntry, PokemonMove,
)
from .decode import decode_string
from .validation import validate_save_bytes
from .layout.gen1_main_data import (
    PARTY_DATA_START, PARTY_DATA_SIZE, BADGES, CURRENT_MAP_ID, PLAYER_X, PLAYER_Y,
    CURRENT_BOX_START, CURRENT_BOX_SIZE, PLAYER_NAME, PLAYER_NAME_SIZE,
    PLAYER_ID, PLAYER_ID_SIZE, CURRENT_BOX_NUMBER, BOXES_INITIALIZED_MASK,
    BOX_NUMBER_MASK,
    BAG_ITEMS, MAX_BAG_ITEMS, MONEY, MONEY_SIZE, PC_ITEMS, MAX_PC_ITEMS,
    POKEDEX_OWNED, POKEDEX_SEEN, POKEDEX_BITFIELD_SIZE,
    RIVAL_NAME, RIVAL_NAME_SIZE,
    TOGGLEABLE_OBJECT_FLAGS, TOGGLEABLE_OBJECT_FLAG_COUNT,
    OBTAINED_HIDDEN_ITEMS_FLAGS, OBTAINED_HIDDEN_ITEMS_FLAG_COUNT,
    PLAYER_STARTER, RIVAL_STARTER, HALL_OF_FAME_TEAM_COUNT, EVENT_FLAGS, EVENT_FLAG_COUNT,
)
from .layout.gen1_banks import STORED_BOX_BANK_STARTS, STORED_BOX_SIZE, STORED_BOXES_PER_BANK
from .layout.gen1_maps import get_map
from .layout.gen1_battle_data import get_move, get_species_base_data, get_type
from .layout.gen1_items import get_item_data
from .mechanics import decode_status, experience_for_level, maximum_pp
from .layout.gen1_party import (
    PARTY_COUNT_OFFSET, SPECIES_LIST_OFFSET, POKEMON_DATA_OFFSET,
    POKEMON_DATA_STRUCT_SIZE, OT_NAMES_OFFSET, OT_NAMES_SIZE, NICKNAMES_OFFSET, NICKNAMES_SIZE,
    FIELD_SPECIES, FIELD_CURRENT_HP, FIELD_LEVEL, FIELD_STATUS, FIELD_TYPE1, FIELD_TYPE2,
    FIELD_CATCH_RATE, FIELD_MOVES, FIELD_OT_ID, FIELD_EXP, FIELD_STAT_EXP, FIELD_DVS, FIELD_PP,
    FIELD_LEVEL_2, FIELD_MAX_HP, FIELD_ATTACK, FIELD_DEFENSE, FIELD_SPEED, FIELD_SPECIAL
)

PARSER_SOURCE = "gen1_red_blue_save_parser"
BADGE_NAMES_BY_BIT = (
    "Boulder", "Cascade", "Thunder", "Rainbow",
    "Soul", "Marsh", "Volcano", "Earth",
)


def _provenance(offset: int, length: int = 1) -> FieldProvenance:
    return FieldProvenance(PARSER_SOURCE, offset, length)


def _decode_bcd(data: bytes) -> int:
    value = 0
    for byte in data:
        value = value * 100 + (byte >> 4) * 10 + (byte & 0x0F)
    return value


def _parse_item_list(reader: SaveReader, offset: int, maximum: int) -> list[InventoryEntry]:
    count = reader.read_byte(offset)
    if count > maximum:
        raise ValueError(f"Invalid item count {count}, maximum is {maximum}")
    entries = []
    for index in range(count):
        item_id = reader.read_byte(offset + 1 + index * 2)
        item = get_item_data(item_id)
        entries.append(InventoryEntry(
            item_id=item_id,
            quantity=reader.read_byte(offset + 2 + index * 2),
            provenance=_provenance(offset + 1 + index * 2, 2),
            stable_id=item.stable_id,
            display_name=item.display_name,
        ))
    return entries


def _parse_pokedex_bitfield(data: bytes) -> list[int]:
    return [
        dex_number
        for dex_number in range(1, 152)
        if data[(dex_number - 1) // 8] & (1 << ((dex_number - 1) % 8))
    ]


def _parse_set_bits(data: bytes, bit_count: int) -> frozenset[int]:
    return frozenset(
        bit for bit in range(bit_count)
        if data[bit // 8] & (1 << (bit % 8))
    )


def _read_stat_exp(reader: SaveReader, struct_start: int) -> list[int]:
    return [reader.read_int(struct_start + FIELD_STAT_EXP + index * 2, 2) for index in range(5)]


def _normalized_pokemon_fields(
    *,
    species_id: int,
    type1: int,
    type2: int,
    moves: list[int],
    pp: list[int],
    status: int,
    exp: int,
    level: int,
    struct_start: int,
) -> tuple[list[str], list[PokemonMove], list[str], int | None]:
    type_names = [get_type(type_id).display_name for type_id in (type1, type2)]
    move_details = []
    for index, (move_id, encoded_pp) in enumerate(zip(moves, pp)):
        if move_id == 0:
            continue
        move = get_move(move_id)
        pp_ups = encoded_pp >> 6
        move_details.append(PokemonMove(
            move_id=move_id,
            stable_id=move.stable_id,
            display_name=move.display_name,
            current_pp=encoded_pp & 0x3F,
            pp_ups=pp_ups,
            maximum_pp=maximum_pp(move, pp_ups),
            provenance=_provenance(struct_start + FIELD_MOVES + index),
        ))
    species = get_species_base_data(species_id)
    next_level_exp = experience_for_level(species.growth_rate, level + 1) if level < 100 else None
    experience_to_next = next_level_exp - exp if next_level_exp is not None else None
    return type_names, move_details, decode_status(status), experience_to_next
from .layout.gen1_box import (
    BOX_COUNT_OFFSET, BOX_POKEMON_DATA_OFFSET, BOX_POKEMON_DATA_STRUCT_SIZE,
    BOX_OT_NAMES_OFFSET, BOX_NICKNAMES_OFFSET
)

def parse_box(reader: SaveReader, start_offset: int) -> list[BoxMember]:
    count = reader.read_byte(start_offset + BOX_COUNT_OFFSET)
    if count > 20:
        raise ValueError(f"Invalid box count: {count}")
    
    box = []
    for i in range(count):
        struct_start = start_offset + BOX_POKEMON_DATA_OFFSET + (i * BOX_POKEMON_DATA_STRUCT_SIZE)
        
        species_id = reader.read_byte(struct_start + FIELD_SPECIES)
        current_hp = reader.read_int(struct_start + FIELD_CURRENT_HP, 2)
        level = reader.read_byte(struct_start + FIELD_LEVEL)
        status = reader.read_byte(struct_start + FIELD_STATUS)
        type1 = reader.read_byte(struct_start + FIELD_TYPE1)
        type2 = reader.read_byte(struct_start + FIELD_TYPE2)
        catch_rate = reader.read_byte(struct_start + FIELD_CATCH_RATE)
        
        moves = []
        for m in range(4):
            moves.append(reader.read_byte(struct_start + FIELD_MOVES + m))
            
        ot_id = reader.read_int(struct_start + FIELD_OT_ID, 2)
        exp = reader.read_int(struct_start + FIELD_EXP, 3)
        dvs = reader.read_int(struct_start + FIELD_DVS, 2)
        stat_exp = _read_stat_exp(reader, struct_start)
        
        pp = []
        for p in range(4):
            pp.append(reader.read_byte(struct_start + FIELD_PP + p))
            
        # OT Name and Nickname
        ot_name_start = start_offset + BOX_OT_NAMES_OFFSET + (i * 11)
        ot_name = decode_string(reader.read_bytes(ot_name_start, 11))
        
        nickname_start = start_offset + BOX_NICKNAMES_OFFSET + (i * 11)
        nickname = decode_string(reader.read_bytes(nickname_start, 11))
        type_names, move_details, status_conditions, experience_to_next = _normalized_pokemon_fields(
            species_id=species_id, type1=type1, type2=type2, moves=moves, pp=pp,
            status=status, exp=exp, level=level, struct_start=struct_start,
        )
        box.append(BoxMember(
            species_id=species_id, current_hp=current_hp, level=level,
            status=status, type1=type1, type2=type2, catch_rate=catch_rate,
            moves=moves, ot_id=ot_id, exp=exp, dvs=dvs, pp=pp,
            original_trainer_name=ot_name, nickname=nickname,
            provenance={
                "species_id": _provenance(struct_start + FIELD_SPECIES),
                "level": _provenance(struct_start + FIELD_LEVEL),
                "current_hp": _provenance(struct_start + FIELD_CURRENT_HP, 2),
                "original_trainer_name": _provenance(ot_name_start, 11),
                "nickname": _provenance(nickname_start, 11),
            },
            type_names=type_names,
            move_details=move_details,
            status_conditions=status_conditions,
            stat_exp=stat_exp,
            experience_to_next_level=experience_to_next,
        ))
        
    return box

def parse_party(reader: SaveReader) -> list[PartyMember]:
    count = reader.read_byte(PARTY_DATA_START + PARTY_COUNT_OFFSET)
    if count > 6:
        raise ValueError(f"Invalid party count: {count}")
    
    party = []
    for i in range(count):
        struct_start = PARTY_DATA_START + POKEMON_DATA_OFFSET + (i * POKEMON_DATA_STRUCT_SIZE)
        
        # Read fields
        species_id = reader.read_byte(struct_start + FIELD_SPECIES)
        current_hp = reader.read_int(struct_start + FIELD_CURRENT_HP, 2)
        
        # Authoritative level for Party Pokemon is FIELD_LEVEL_2 (0x21)
        level = reader.read_byte(struct_start + FIELD_LEVEL_2)
        box_level = reader.read_byte(struct_start + FIELD_LEVEL)
        
        status = reader.read_byte(struct_start + FIELD_STATUS)
        type1 = reader.read_byte(struct_start + FIELD_TYPE1)
        type2 = reader.read_byte(struct_start + FIELD_TYPE2)
        catch_rate = reader.read_byte(struct_start + FIELD_CATCH_RATE)
        
        moves = []
        for m in range(4):
            moves.append(reader.read_byte(struct_start + FIELD_MOVES + m))
            
        ot_id = reader.read_int(struct_start + FIELD_OT_ID, 2)
        exp = reader.read_int(struct_start + FIELD_EXP, 3)
        dvs = reader.read_int(struct_start + FIELD_DVS, 2)
        stat_exp = _read_stat_exp(reader, struct_start)
        
        pp = []
        for p in range(4):
            pp.append(reader.read_byte(struct_start + FIELD_PP + p))
            
        level_2 = reader.read_byte(struct_start + FIELD_LEVEL_2)
        max_hp = reader.read_int(struct_start + FIELD_MAX_HP, 2)
        attack = reader.read_int(struct_start + FIELD_ATTACK, 2)
        defense = reader.read_int(struct_start + FIELD_DEFENSE, 2)
        speed = reader.read_int(struct_start + FIELD_SPEED, 2)
        special = reader.read_int(struct_start + FIELD_SPECIAL, 2)
        
        # OT Name and Nickname
        ot_name_start = PARTY_DATA_START + OT_NAMES_OFFSET + (i * 11)
        ot_name_bytes = reader.read_bytes(ot_name_start, 11)
        ot_name = decode_string(ot_name_bytes)
        
        nickname_start = PARTY_DATA_START + NICKNAMES_OFFSET + (i * 11)
        nickname_bytes = reader.read_bytes(nickname_start, 11)
        nickname = decode_string(nickname_bytes)
        type_names, move_details, status_conditions, experience_to_next = _normalized_pokemon_fields(
            species_id=species_id, type1=type1, type2=type2, moves=moves, pp=pp,
            status=status, exp=exp, level=level, struct_start=struct_start,
        )
        party.append(PartyMember(
            species_id=species_id, current_hp=current_hp, max_hp=max_hp, level=level,
            box_level=box_level, status=status, type1=type1, type2=type2, catch_rate=catch_rate, 
            moves=moves, ot_id=ot_id, exp=exp, dvs=dvs, pp=pp, attack=attack, defense=defense,
            speed=speed, special=special, original_trainer_name=ot_name, nickname=nickname,
            provenance={
                "species_id": _provenance(struct_start + FIELD_SPECIES),
                "level": _provenance(struct_start + FIELD_LEVEL_2),
                "box_level": _provenance(struct_start + FIELD_LEVEL),
                "current_hp": _provenance(struct_start + FIELD_CURRENT_HP, 2),
                "max_hp": _provenance(struct_start + FIELD_MAX_HP, 2),
                "original_trainer_name": _provenance(ot_name_start, 11),
                "nickname": _provenance(nickname_start, 11),
            },
            type_names=type_names,
            move_details=move_details,
            status_conditions=status_conditions,
            stat_exp=stat_exp,
            experience_to_next_level=experience_to_next,
        ))
        
    return party


def parse_pc_boxes(
    reader: SaveReader,
    *,
    current_box_index: int,
    boxes_initialized: bool,
    current_box: list[BoxMember],
) -> list[StorageBox]:
    boxes: list[StorageBox] = []
    if boxes_initialized:
        for bank_start in STORED_BOX_BANK_STARTS:
            for bank_box_index in range(STORED_BOXES_PER_BANK):
                box_index = len(boxes)
                box_start = bank_start + bank_box_index * STORED_BOX_SIZE
                boxes.append(StorageBox(
                    index=box_index,
                    status=StorageBoxStatus.STORED,
                    members=parse_box(reader, box_start),
                    checksum_verified=True,
                    provenance=_provenance(box_start, STORED_BOX_SIZE),
                ))
    else:
        boxes = [
            StorageBox(
                index=index,
                status=StorageBoxStatus.UNINITIALIZED,
                members=[],
                checksum_verified=None,
            )
            for index in range(12)
        ]

    if 0 <= current_box_index < 12:
        boxes[current_box_index] = StorageBox(
            index=current_box_index,
            status=StorageBoxStatus.CURRENT_CACHE,
            members=current_box,
            checksum_verified=True,
            provenance=_provenance(CURRENT_BOX_START, CURRENT_BOX_SIZE),
        )
    return boxes

def parse_save_bytes(data: bytes, expected_version: GameVersion | None = None) -> SaveState:
    """Validate and parse a complete 32 KiB Red/Blue SRAM image."""
    if expected_version is not None and not isinstance(expected_version, GameVersion):
        raise TypeError("expected_version must be a GameVersion or None")
    validation = validate_save_bytes(data)
    diagnostics = list(validation.diagnostics)
    errors = [item.message for item in diagnostics if item.severity is DiagnosticSeverity.ERROR]

    if not validation.can_parse:
        return SaveState(
            is_valid=False,
            validation_errors=errors,
            party=[],
            current_box=[],
            badges=0,
            current_map_id=0,
            game_version=expected_version,
            game_version_source="run_configuration" if expected_version is not None else None,
            status=validation.status,
            diagnostics=diagnostics,
        )

    reader = SaveReader(data)
    try:
        player_name = decode_string(reader.read_bytes(PLAYER_NAME, PLAYER_NAME_SIZE))
        player_id = reader.read_int(PLAYER_ID, PLAYER_ID_SIZE)
        rival_name = decode_string(reader.read_bytes(RIVAL_NAME, RIVAL_NAME_SIZE))
        money = _decode_bcd(reader.read_bytes(MONEY, MONEY_SIZE))
        bag_items = _parse_item_list(reader, BAG_ITEMS, MAX_BAG_ITEMS)
        pc_items = _parse_item_list(reader, PC_ITEMS, MAX_PC_ITEMS)
        pokedex_owned = _parse_pokedex_bitfield(reader.read_bytes(POKEDEX_OWNED, POKEDEX_BITFIELD_SIZE))
        pokedex_seen = _parse_pokedex_bitfield(reader.read_bytes(POKEDEX_SEEN, POKEDEX_BITFIELD_SIZE))
        badges = reader.read_byte(BADGES)
        earned_badges = [
            name for bit, name in enumerate(BADGE_NAMES_BY_BIT)
            if badges & (1 << bit)
        ]
        current_map_id = reader.read_byte(CURRENT_MAP_ID)
        player_x = reader.read_byte(PLAYER_X)
        player_y = reader.read_byte(PLAYER_Y)
        current_map = get_map(current_map_id)
        current_box_raw = reader.read_byte(CURRENT_BOX_NUMBER)
        current_box_index = current_box_raw & BOX_NUMBER_MASK
        boxes_initialized = bool(current_box_raw & BOXES_INITIALIZED_MASK)
        player_starter_id = reader.read_byte(PLAYER_STARTER)
        rival_starter_id = reader.read_byte(RIVAL_STARTER)
        hall_of_fame_team_count = reader.read_byte(HALL_OF_FAME_TEAM_COUNT)
        toggleable_object_flags = _parse_set_bits(
            reader.read_bytes(TOGGLEABLE_OBJECT_FLAGS, TOGGLEABLE_OBJECT_FLAG_COUNT // 8),
            TOGGLEABLE_OBJECT_FLAG_COUNT,
        )
        obtained_hidden_item_flags = _parse_set_bits(
            reader.read_bytes(
                OBTAINED_HIDDEN_ITEMS_FLAGS,
                (OBTAINED_HIDDEN_ITEMS_FLAG_COUNT + 7) // 8,
            ),
            OBTAINED_HIDDEN_ITEMS_FLAG_COUNT,
        )
        event_flags = _parse_set_bits(
            reader.read_bytes(EVENT_FLAGS, EVENT_FLAG_COUNT // 8), EVENT_FLAG_COUNT
        )
        party = parse_party(reader)
        current_box = parse_box(reader, CURRENT_BOX_START)
        pc_boxes = parse_pc_boxes(
            reader,
            current_box_index=current_box_index,
            boxes_initialized=boxes_initialized,
            current_box=current_box,
        )
    except (IndexError, ValueError) as exc:
        # This should only be reachable for an invariant missing from validation.
        diagnostic = Diagnostic(
            "unexpected_parse_failure",
            DiagnosticSeverity.ERROR,
            f"Validated data could not be parsed: {exc}",
        )
        diagnostics.append(diagnostic)
        errors.append(diagnostic.message)
        return SaveState(
            is_valid=False,
            validation_errors=errors,
            party=[],
            current_box=[],
            badges=0,
            current_map_id=0,
            game_version=expected_version,
            game_version_source="run_configuration" if expected_version is not None else None,
            status=ParseStatus.INVALID,
            diagnostics=diagnostics,
        )

    return SaveState(
        is_valid=True,
        validation_errors=errors,
        party=party,
        current_box=current_box,
        badges=badges,
        earned_badges=earned_badges,
        current_map_id=current_map_id,
        player_x=player_x,
        player_y=player_y,
        location_id=current_map.stable_id if current_map else None,
        location_name=current_map.display_name if current_map else None,
        player_name=player_name,
        player_id=player_id,
        rival_name=rival_name,
        money=money,
        bag_items=bag_items,
        pc_items=pc_items,
        pokedex_owned=pokedex_owned,
        pokedex_seen=pokedex_seen,
        current_box_index=current_box_index,
        boxes_initialized=boxes_initialized,
        player_starter_id=player_starter_id,
        rival_starter_id=rival_starter_id,
        hall_of_fame_team_count=hall_of_fame_team_count,
        toggleable_object_flags=toggleable_object_flags,
        obtained_hidden_item_flags=obtained_hidden_item_flags,
        event_flags=event_flags,
        pc_boxes=pc_boxes,
        game_version=expected_version,
        game_version_source="run_configuration" if expected_version is not None else None,
        status=validation.status,
        diagnostics=diagnostics,
        provenance={
            "player_name": _provenance(PLAYER_NAME, PLAYER_NAME_SIZE),
            "player_id": _provenance(PLAYER_ID, PLAYER_ID_SIZE),
            "rival_name": _provenance(RIVAL_NAME, RIVAL_NAME_SIZE),
            "money": _provenance(MONEY, MONEY_SIZE),
            "bag_items": _provenance(BAG_ITEMS, 1 + len(bag_items) * 2 + 1),
            "pc_items": _provenance(PC_ITEMS, 1 + len(pc_items) * 2 + 1),
            "pokedex_owned": _provenance(POKEDEX_OWNED, POKEDEX_BITFIELD_SIZE),
            "pokedex_seen": _provenance(POKEDEX_SEEN, POKEDEX_BITFIELD_SIZE),
            "badges": _provenance(BADGES),
            "current_map_id": _provenance(CURRENT_MAP_ID),
            "player_x": _provenance(PLAYER_X),
            "player_y": _provenance(PLAYER_Y),
            "current_box_index": _provenance(CURRENT_BOX_NUMBER),
            "player_starter_id": _provenance(PLAYER_STARTER),
            "rival_starter_id": _provenance(RIVAL_STARTER),
            "hall_of_fame_team_count": _provenance(HALL_OF_FAME_TEAM_COUNT),
            "toggleable_object_flags": _provenance(
                TOGGLEABLE_OBJECT_FLAGS, TOGGLEABLE_OBJECT_FLAG_COUNT // 8
            ),
            "obtained_hidden_item_flags": _provenance(
                OBTAINED_HIDDEN_ITEMS_FLAGS,
                (OBTAINED_HIDDEN_ITEMS_FLAG_COUNT + 7) // 8,
            ),
            "event_flags": _provenance(EVENT_FLAGS, EVENT_FLAG_COUNT // 8),
            "party": _provenance(PARTY_DATA_START, PARTY_DATA_SIZE),
            "current_box": _provenance(CURRENT_BOX_START, CURRENT_BOX_SIZE),
        },
    )


def parse_save(file_path: str, expected_version: GameVersion | None = None) -> SaveState:
    """Compatibility wrapper for callers that provide a filesystem path."""
    with open(file_path, "rb") as file:
        return parse_save_bytes(file.read(), expected_version=expected_version)
