"""Pokémon Red/Blue internal species indexes.

These are not National Pokédex numbers. MissingNo indexes and the three special
battle sprite indexes are intentionally excluded from valid owned Pokémon.
Source: pret/pokered constants/pokemon_constants.asm.
"""

SPECIES_INDEX = {
    0x01: "Rhydon", 0x02: "Kangaskhan", 0x03: "Nidoran♂", 0x04: "Clefairy",
    0x05: "Spearow", 0x06: "Voltorb", 0x07: "Nidoking", 0x08: "Slowbro",
    0x09: "Ivysaur", 0x0A: "Exeggutor", 0x0B: "Lickitung", 0x0C: "Exeggcute",
    0x0D: "Grimer", 0x0E: "Gengar", 0x0F: "Nidoran♀", 0x10: "Nidoqueen",
    0x11: "Cubone", 0x12: "Rhyhorn", 0x13: "Lapras", 0x14: "Arcanine",
    0x15: "Mew", 0x16: "Gyarados", 0x17: "Shellder", 0x18: "Tentacool",
    0x19: "Gastly", 0x1A: "Scyther", 0x1B: "Staryu", 0x1C: "Blastoise",
    0x1D: "Pinsir", 0x1E: "Tangela", 0x21: "Growlithe", 0x22: "Onix",
    0x23: "Fearow", 0x24: "Pidgey", 0x25: "Slowpoke", 0x26: "Kadabra",
    0x27: "Graveler", 0x28: "Chansey", 0x29: "Machoke", 0x2A: "Mr. Mime",
    0x2B: "Hitmonlee", 0x2C: "Hitmonchan", 0x2D: "Arbok", 0x2E: "Parasect",
    0x2F: "Psyduck", 0x30: "Drowzee", 0x31: "Golem", 0x33: "Magmar",
    0x35: "Electabuzz", 0x36: "Magneton", 0x37: "Koffing", 0x39: "Mankey",
    0x3A: "Seel", 0x3B: "Diglett", 0x3C: "Tauros", 0x40: "Farfetch'd",
    0x41: "Venonat", 0x42: "Dragonite", 0x46: "Doduo", 0x47: "Poliwag",
    0x48: "Jynx", 0x49: "Moltres", 0x4A: "Articuno", 0x4B: "Zapdos",
    0x4C: "Ditto", 0x4D: "Meowth", 0x4E: "Krabby", 0x52: "Vulpix",
    0x53: "Ninetales", 0x54: "Pikachu", 0x55: "Raichu", 0x58: "Dratini",
    0x59: "Dragonair", 0x5A: "Kabuto", 0x5B: "Kabutops", 0x5C: "Horsea",
    0x5D: "Seadra", 0x60: "Sandshrew", 0x61: "Sandslash", 0x62: "Omanyte",
    0x63: "Omastar", 0x64: "Jigglypuff", 0x65: "Wigglytuff", 0x66: "Eevee",
    0x67: "Flareon", 0x68: "Jolteon", 0x69: "Vaporeon", 0x6A: "Machop",
    0x6B: "Zubat", 0x6C: "Ekans", 0x6D: "Paras", 0x6E: "Poliwhirl",
    0x6F: "Poliwrath", 0x70: "Weedle", 0x71: "Kakuna", 0x72: "Beedrill",
    0x74: "Dodrio", 0x75: "Primeape", 0x76: "Dugtrio", 0x77: "Venomoth",
    0x78: "Dewgong", 0x7B: "Caterpie", 0x7C: "Metapod", 0x7D: "Butterfree",
    0x7E: "Machamp", 0x80: "Golduck", 0x81: "Hypno", 0x82: "Golbat",
    0x83: "Mewtwo", 0x84: "Snorlax", 0x85: "Magikarp", 0x88: "Muk",
    0x8A: "Kingler", 0x8B: "Cloyster", 0x8D: "Electrode", 0x8E: "Clefable",
    0x8F: "Weezing", 0x90: "Persian", 0x91: "Marowak", 0x93: "Haunter",
    0x94: "Abra", 0x95: "Alakazam", 0x96: "Pidgeotto", 0x97: "Pidgeot",
    0x98: "Starmie", 0x99: "Bulbasaur", 0x9A: "Venusaur", 0x9B: "Tentacruel",
    0x9D: "Goldeen", 0x9E: "Seaking", 0xA3: "Ponyta", 0xA4: "Rapidash",
    0xA5: "Rattata", 0xA6: "Raticate", 0xA7: "Nidorino", 0xA8: "Nidorina",
    0xA9: "Geodude", 0xAA: "Porygon", 0xAB: "Aerodactyl", 0xAD: "Magnemite",
    0xB0: "Charmander", 0xB1: "Squirtle", 0xB2: "Charmeleon", 0xB3: "Wartortle",
    0xB4: "Charizard", 0xB9: "Oddish", 0xBA: "Gloom", 0xBB: "Vileplume",
    0xBC: "Bellsprout", 0xBD: "Weepinbell", 0xBE: "Victreebel",
}


def is_valid_species_id(species_id: int) -> bool:
    return species_id in SPECIES_INDEX


def get_species_name(species_id: int) -> str:
    return SPECIES_INDEX.get(species_id, f"Unknown ({species_id:#04x})")
