from dataclasses import dataclass, field
from enum import Enum
from typing import List


class ParseStatus(str, Enum):
    VALID = "valid"
    VALID_WITH_WARNINGS = "valid_with_warnings"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


class GameVersion(str, Enum):
    RED = "red"
    BLUE = "blue"


class DiagnosticSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: DiagnosticSeverity
    message: str
    offset: int | None = None
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class FieldProvenance:
    source: str
    offset: int
    length: int
    confidence: float = 1.0


@dataclass(frozen=True)
class PokemonMove:
    move_id: int
    stable_id: str
    display_name: str
    current_pp: int
    pp_ups: int
    maximum_pp: int
    provenance: FieldProvenance


class StorageBoxStatus(str, Enum):
    CURRENT_CACHE = "current_cache"
    STORED = "stored"
    UNINITIALIZED = "uninitialized"

@dataclass
class PartyMember:
    species_id: int
    current_hp: int
    max_hp: int
    level: int
    box_level: int
    status: int
    type1: int
    type2: int
    catch_rate: int
    moves: List[int]
    ot_id: int
    exp: int
    dvs: int
    pp: List[int]
    attack: int
    defense: int
    speed: int
    special: int
    original_trainer_name: str
    nickname: str
    provenance: dict[str, FieldProvenance] = field(default_factory=dict)
    type_names: List[str] = field(default_factory=list)
    move_details: List[PokemonMove] = field(default_factory=list)
    status_conditions: List[str] = field(default_factory=list)
    stat_exp: List[int] = field(default_factory=list)
    experience_to_next_level: int | None = None

@dataclass
class BoxMember:
    species_id: int
    current_hp: int
    level: int
    status: int
    type1: int
    type2: int
    catch_rate: int
    moves: List[int]
    ot_id: int
    exp: int
    dvs: int
    pp: List[int]
    original_trainer_name: str
    nickname: str
    provenance: dict[str, FieldProvenance] = field(default_factory=dict)
    type_names: List[str] = field(default_factory=list)
    move_details: List[PokemonMove] = field(default_factory=list)
    status_conditions: List[str] = field(default_factory=list)
    stat_exp: List[int] = field(default_factory=list)
    experience_to_next_level: int | None = None


@dataclass
class StorageBox:
    index: int
    status: StorageBoxStatus
    members: List[BoxMember]
    checksum_verified: bool | None
    provenance: FieldProvenance | None = None


@dataclass(frozen=True)
class InventoryEntry:
    item_id: int
    quantity: int
    provenance: FieldProvenance
    stable_id: str = ""
    display_name: str = ""

@dataclass
class SaveState:
    is_valid: bool
    validation_errors: List[str]
    party: List[PartyMember]
    current_box: List[BoxMember]
    badges: int
    current_map_id: int
    player_x: int | None = None
    player_y: int | None = None
    location_id: str | None = None
    location_name: str | None = None
    player_name: str = ""
    player_id: int = 0
    rival_name: str = ""
    money: int = 0
    bag_items: List[InventoryEntry] = field(default_factory=list)
    pc_items: List[InventoryEntry] = field(default_factory=list)
    pokedex_owned: List[int] = field(default_factory=list)
    pokedex_seen: List[int] = field(default_factory=list)
    earned_badges: List[str] = field(default_factory=list)
    game_version: GameVersion | None = None
    game_version_source: str | None = None
    current_box_index: int = 0
    boxes_initialized: bool = False
    player_starter_id: int | None = None
    rival_starter_id: int | None = None
    hall_of_fame_team_count: int = 0
    toggleable_object_flags: frozenset[int] = frozenset()
    obtained_hidden_item_flags: frozenset[int] = frozenset()
    event_flags: frozenset[int] = frozenset()
    pc_boxes: List[StorageBox] = field(default_factory=list)
    status: ParseStatus = ParseStatus.INVALID
    diagnostics: List[Diagnostic] = field(default_factory=list)
    provenance: dict[str, FieldProvenance] = field(default_factory=dict)
