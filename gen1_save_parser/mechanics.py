"""Deterministic Pokémon Red/Blue mechanics used for parser invariants."""

from math import isqrt

from .layout.gen1_battle_data import MoveDefinition, SpeciesBaseData


def experience_for_level(growth_rate: str, level: int) -> int:
    if not 1 <= level <= 100:
        raise ValueError("level must be in 1..100")
    cubic = level ** 3
    formulas = {
        "medium_fast": cubic,
        "slightly_fast": (3 * cubic) // 4 + 10 * level ** 2 - 30,
        "slightly_slow": (3 * cubic) // 4 + 20 * level ** 2 - 70,
        "medium_slow": (6 * cubic) // 5 - 15 * level ** 2 + 100 * level - 140,
        "fast": (4 * cubic) // 5,
        "slow": (5 * cubic) // 4,
    }
    try:
        return max(0, formulas[growth_rate])
    except KeyError as exc:
        raise ValueError(f"unknown growth rate {growth_rate!r}") from exc


def decode_dvs(dvs: int) -> dict[str, int]:
    attack = (dvs >> 12) & 0x0F
    defense = (dvs >> 8) & 0x0F
    speed = (dvs >> 4) & 0x0F
    special = dvs & 0x0F
    hp = (
        ((attack & 1) << 3)
        | ((defense & 1) << 2)
        | ((speed & 1) << 1)
        | (special & 1)
    )
    return {"hp": hp, "attack": attack, "defense": defense, "speed": speed, "special": special}


def _stat(base: int, dv: int, stat_exp: int, level: int, *, hp: bool) -> int:
    root = isqrt(stat_exp)
    ceil_root = root if root * root == stat_exp else root + 1
    effort = min(255, ceil_root) // 4
    core = (((base + dv) * 2 + effort) * level) // 100
    value = core + level + 10 if hp else core + 5
    return min(999, value)


def calculate_party_stats(
    species: SpeciesBaseData,
    dvs: int,
    stat_exp: list[int],
    level: int,
) -> dict[str, int]:
    if len(stat_exp) != 5:
        raise ValueError("stat_exp must contain five values")
    decoded = decode_dvs(dvs)
    bases = (
        species.base_hp,
        species.base_attack,
        species.base_defense,
        species.base_speed,
        species.base_special,
    )
    names = ("hp", "attack", "defense", "speed", "special")
    return {
        name: _stat(base, decoded[name], effort, level, hp=name == "hp")
        for name, base, effort in zip(names, bases, stat_exp)
    }


def maximum_pp(move: MoveDefinition, pp_ups: int) -> int:
    if not 0 <= pp_ups <= 3:
        raise ValueError("pp_ups must be in 0..3")
    # Gen I caps the one-fifth bonus from each PP Up at seven points.
    return move.base_pp + min(move.base_pp // 5, 7) * pp_ups


def decode_status(status: int) -> list[str]:
    conditions = []
    if status & 0x07:
        conditions.append("sleep")
    for mask, name in ((0x08, "poison"), (0x10, "burn"), (0x20, "freeze"), (0x40, "paralysis")):
        if status & mask:
            conditions.append(name)
    return conditions
