"""Canonical Pokémon Red/Blue inventory names from pret/pokered.

Source commit: 0cd19d3b877b7dc66d12c7050bed9a7f38154d4b
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class ItemData:
    item_id: int
    stable_id: str
    display_name: str


_NORMAL_NAMES = (
    "Master Ball", "Ultra Ball", "Great Ball", "Poké Ball", "Town Map", "Bicycle",
    "Surfboard", "Safari Ball", "Pokédex", "Moon Stone", "Antidote", "Burn Heal",
    "Ice Heal", "Awakening", "Parlyz Heal", "Full Restore", "Max Potion",
    "Hyper Potion", "Super Potion", "Potion", "Boulder Badge", "Cascade Badge",
    "Thunder Badge", "Rainbow Badge", "Soul Badge", "Marsh Badge", "Volcano Badge",
    "Earth Badge", "Escape Rope", "Repel", "Old Amber", "Fire Stone", "Thunder Stone",
    "Water Stone", "HP Up", "Protein", "Iron", "Carbos", "Calcium", "Rare Candy",
    "Dome Fossil", "Helix Fossil", "Secret Key", "Unused Item 2C", "Bike Voucher",
    "X Accuracy", "Leaf Stone", "Card Key", "Nugget", "PP Up", "Poké Doll",
    "Full Heal", "Revive", "Max Revive", "Guard Spec.", "Super Repel", "Max Repel",
    "Dire Hit", "Coin", "Fresh Water", "Soda Pop", "Lemonade", "S.S. Ticket",
    "Gold Teeth", "X Attack", "X Defend", "X Speed", "X Special", "Coin Case",
    "Oak's Parcel", "Itemfinder", "Silph Scope", "Poké Flute", "Lift Key", "Exp. All",
    "Old Rod", "Good Rod", "Super Rod", "PP Up", "Ether", "Max Ether", "Elixer",
    "Max Elixer",
)

_HM_MOVES = ("Cut", "Fly", "Surf", "Strength", "Flash")
_TM_MOVES = (
    "Mega Punch", "Razor Wind", "Swords Dance", "Whirlwind", "Mega Kick", "Toxic",
    "Horn Drill", "Body Slam", "Take Down", "Double-Edge", "Bubble Beam", "Water Gun",
    "Ice Beam", "Blizzard", "Hyper Beam", "Pay Day", "Submission", "Counter",
    "Seismic Toss", "Rage", "Mega Drain", "Solar Beam", "Dragon Rage", "Thunderbolt",
    "Thunder", "Earthquake", "Fissure", "Dig", "Psychic", "Teleport", "Mimic",
    "Double Team", "Reflect", "Bide", "Metronome", "Self-Destruct", "Egg Bomb",
    "Fire Blast", "Swift", "Skull Bash", "Soft-Boiled", "Dream Eater", "Sky Attack",
    "Rest", "Thunder Wave", "Psywave", "Explosion", "Rock Slide", "Tri Attack",
    "Substitute",
)


def _stable_id(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", ascii_name.casefold()).strip("_")


ITEMS: dict[int, ItemData] = {
    index: ItemData(index, _stable_id(name), name)
    for index, name in enumerate(_NORMAL_NAMES, start=1)
}
ITEMS.update({
    0xC4 + index: ItemData(0xC4 + index, f"hm{index + 1:02d}", f"HM{index + 1:02d} ({move})")
    for index, move in enumerate(_HM_MOVES)
})
ITEMS.update({
    0xC9 + index: ItemData(0xC9 + index, f"tm{index + 1:02d}", f"TM{index + 1:02d} ({move})")
    for index, move in enumerate(_TM_MOVES)
})


def get_item_data(item_id: int) -> ItemData:
    return ITEMS.get(item_id, ItemData(item_id, f"unknown_{item_id:02x}", f"Unknown item 0x{item_id:02X}"))
