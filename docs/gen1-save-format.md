# Pokémon Red/Blue save parser specification

## Scope

This document records the fields that the parser currently exposes and the
evidence required before adding more. It targets 32 KiB SRAM images from the
English Pokémon Red and Blue releases represented by `pret/pokered`.

The save is an observation of game state. It is not Nuzlocke history and it is
not proof of which version was played, whether resets occurred, or whether the
save was modified.

## Source hierarchy

1. [`pret/pokered` disassembly](https://github.com/pret/pokered)
2. Reproducible observations from known saves
3. Independent technical documentation used only as corroboration

The implementation must cite a source and add a test before exposing a new
field as authoritative.

## Container

| Property | Value | Implementation |
| --- | ---: | --- |
| SRAM image size | `0x8000` (32,768) bytes | `layout/gen1_banks.py` |
| SRAM bank size | `0x2000` (8,192) bytes | `layout/gen1_banks.py` |
| Number of banks | 4 | `layout/gen1_banks.py` |

Files with headers, emulator metadata, compression, or any size other than
32,768 bytes are currently unsupported and rejected rather than guessed.

## Main saved-data region

Offsets below are absolute file offsets.

| Field | Offset | Length | Status |
| --- | ---: | ---: | --- |
| Player name | `0x2598` | 11 | Parsed and validated |
| Pokédex owned | `0x25A3` | 19 | Parsed as National Dex numbers |
| Pokédex seen | `0x25B6` | 19 | Parsed as National Dex numbers |
| Bag items | `0x25C9` | `0x2A` | Parsed and validated |
| Money | `0x25F3` | 3 | Parsed from binary-coded decimal |
| Rival name | `0x25F6` | 11 | Parsed and validated |
| Player ID | `0x2605` | 2 | Parsed big-endian |
| Badges bitfield | `0x2602` | 1 | Exposed as raw bitfield |
| Current map ID | `0x260A` | 1 | Raw ID retained and normalized |
| Player Y/X tile coordinates | `0x260D/0x260E` | 1 each | Parsed and map-bounds validated |
| PC item storage | `0x27E6` | `0x68` | Parsed and validated |
| Current box number/flags | `0x284C` | 1 | Parsed |
| Hall of Fame team count | `0x284E` | 1 | Parsed |
| Toggleable-object flags | `0x2852` | 32 | Parsed as set global indexes |
| Obtained hidden-item flags | `0x299C` | 14 | Parsed as set indexes |
| Rival/player starter | `0x29C1`/`0x29C3` | 1 each | Parsed as internal species IDs |
| General event flags | `0x29F3` | 320 | Parsed as set event indexes |
| Party data | `0x2F2C` | `0x194` | Parsed |
| Current-box cache | `0x30C0` | `0x462` | Parsed |
| Main checksum | `0x3523` | 1 | Validated |

The main checksum covers `0x2598..0x3522` inclusive. Starting from zero, add
each byte modulo 256 and then complement the result. The stored value at
`0x3523` must equal that result. This follows
[`CalcCheckSum` and `SaveMainData`](https://github.com/pret/pokered/blob/master/engine/menus/save.asm).

### Names and text

Player name, rival name, Pokémon nickname, and Pokémon original-trainer name
are distinct fields. Every exposed name must contain a `0x50` terminator within
its fixed 11-byte allocation, and every byte before the terminator must exist
in the English Gen I character map. Empty, unknown, or unterminated strings
invalidate the parse instead of being shown as trusted text.

For the current golden fixture, the player name is `FLAMER`; the Pokémon
nicknames are independently parsed as `Potion`, `Keeda`, and `RealFlamer`.

### Money and item lists

Money is six decimal digits stored as three BCD bytes. Any nibble above nine is
invalid. Item lists store a count followed by `(item ID, quantity)` pairs and a
`0xFF` terminator. Bag capacity is twenty entries and PC item capacity is fifty.
Unknown/glitch item IDs and zero quantities remain observable but produce
warnings; they are never silently converted to canonical items.

### Pokédex and badges

Pokédex bitfields use National Pokédex order, unlike Pokémon structures, which
use internal species indexes. Only Dex numbers 1–151 are exposed. Badge bits
are normalized to the eight named Kanto badges while the raw byte is retained.

## Party collection

The collection starts at `0x2F2C` and contains:

| Relative offset | Content |
| ---: | --- |
| `0x000` | Count, range 0–6 |
| `0x001` | Species list, followed immediately by `0xFF` |
| `0x008` | Six 44-byte party Pokémon structures |
| `0x110` | Six 11-byte original-trainer names |
| `0x152` | Six 11-byte nicknames |

For every occupied entry, the species-list ID must match the structure ID.
The structure layout is sourced from
[`pokemon_data_constants.asm`](https://github.com/pret/pokered/blob/master/constants/pokemon_data_constants.asm).
The expanded party level at structure offset `0x21` is authoritative for a
party Pokémon; offset `0x03` is the boxed-form level byte.

Current invariants:

- count is no greater than six;
- list terminator is present at `species_list[count]`;
- listed and structured species IDs agree;
- species is one of the 151 real owned-Pokémon indexes;
- level is between 1 and 100;
- maximum HP is nonzero;
- current HP is not greater than maximum HP.
- the two stored types match canonical species base data;
- move IDs are canonical, packed before empty slots, and empty slots have no PP;
- current PP does not exceed base PP plus the encoded zero-to-three PP Ups;
- reserved or mutually exclusive status bits are rejected;
- experience lies within the threshold interval for the stored level and the
  species' growth curve;
- maximum HP, Attack, Defense, Speed, and Special equal the Gen I calculation
  from base stats, DVs, stat experience, and level.

## Current-box cache

The cache starts at `0x30C0` and contains:

| Relative offset | Content |
| ---: | --- |
| `0x000` | Count, range 0–20 |
| `0x001` | Species list, followed immediately by `0xFF` |
| `0x016` | Twenty 33-byte boxed Pokémon structures |
| `0x2AA` | Twenty 11-byte original-trainer names |
| `0x386` | Twenty 11-byte nicknames |

The same count, terminator, species agreement, species validity, and level
checks apply. Boxed structures do not contain the calculated party stats.

Party-stat validation follows Red/Blue's `CalcStat` routine, including
`ceil(sqrt(stat experience)) / 4` and the 999 stat cap. Using a floor square
root incorrectly rejects legitimate saves near Stat Experience boundaries.

## Persistent PC boxes

Banks 2 and 3 contain boxes 1–6 and 7–12 respectively. Each box is `0x462`
bytes. Each bank stores one checksum over all six boxes and six individual-box
checksums. The parser verifies both levels before exposing initialized storage.

The selected-box byte at `0x284C` uses bit 7 as the game's
`BIT_HAS_CHANGED_BOXES`; the lower seven bits are a zero-based box index. Before
the first box change, banks 2 and 3 remain untouched `0xFF` data. In that state,
the parser exposes only the current-box cache as authoritative and marks the
other eleven boxes `uninitialized`, not empty. After initialization, the
selected box comes from the main-bank cache and the remaining boxes come from
the validated storage banks.

## Species identity

Gen I internal species indexes are not National Pokédex numbers. The complete
real-species mapping comes from
[`pokemon_constants.asm`](https://github.com/pret/pokered/blob/master/constants/pokemon_constants.asm).
MissingNo slots and the fossil/ghost battle-only indexes are rejected for an
owned party or boxed Pokémon. A future explicit ROM-hack mode may use a
different policy, but must not weaken standard Red/Blue validation.

## Battle data and Pokémon mechanics

The canonical registry is generated from `pret/pokered` at pinned commit
`0cd19d3b877b7dc66d12c7050bed9a7f38154d4b`. Its combined imported-source
SHA-256 is
`6281867a7224ca99796dbce014af2f36e38eff1670359c86ee39ed83a764b5fc`.
It contains all 165 move definitions, all 151 species' base stats/types/growth
rates, and the 16 defined type IDs across Gen I's sparse `0x00..0x1A` range.

Move PP bytes use the low six bits for current PP and the high two bits for
the number of PP Ups. Each PP Up adds one fifth of base PP, with that per-item
bonus capped at seven exactly as in Gen I; thus a 40-PP move tops out at 61.
Status uses bits 0–2 for sleep duration and bits 3–6 for poison, burn, freeze,
and paralysis; bit 7 is reserved. A standard save cannot have more than one
major condition simultaneously.

The parser exposes display names and stable IDs while retaining raw IDs and
byte-level provenance. It checks structural/mechanical consistency, but does
not claim that a move is legal for a species at that point in a playthrough:
trade, TM/HM, evolution, and version-specific learnsets require a separate
provenance-aware legality layer.

## Location identity

All 248 Red/Blue map IDs are generated from `pret/pokered`'s
`constants/map_constants.asm` at pinned commit
`0cd19d3b877b7dc66d12c7050bed9a7f38154d4b`. The imported source SHA-256 is
`4129ef4e6908267e554c0308254f2269f1fb8f75b5c529faad6fd14c92119271`.

The parser retains the raw byte and exposes a stable ID plus display name, such
as `0x02 -> pewter_city -> Pewter City`. Unknown IDs invalidate the save;
defined-but-unused maps produce warnings. The generation tool verifies that all
248 sequential IDs are present before producing the registry.

## Parse result contract

The byte-oriented entry points are:

```python
validate_save_bytes(data: bytes) -> ValidationResult
parse_save_bytes(data: bytes) -> SaveState
```

`parse_save(path)` remains a filesystem convenience wrapper. Results use
structured diagnostic codes and one of:

- `valid`
- `valid_with_warnings`
- `invalid`
- `unsupported`

Important decoded fields include their source byte offset and length. A valid
checksum alone does not make structurally inconsistent data valid.

## Known limitations and next verification work

- Red and Blue cannot be distinguished authoritatively from a standalone save.
  The parser accepts an explicit version from run configuration and labels its
  source accordingly; version-specific compatibility evidence is not yet
  implemented.
- Persistent trainer-defeat, obtained-item, starter, Hall of Fame, and general
  event flags are exposed with byte provenance. Player coordinates and outdoor
  connections are available, but collision-aware pathfinding and
  indoor-to-outdoor grouping remain future work.
- The current fixture expectations need a human-maintained provenance record
  confirming the in-game values independently of this parser.
- Move learnset legality and version-specific availability are not evaluated.
- Catch rate is retained without requiring the species' base catch rate;
  cross-generation trades can legitimately repurpose that byte.
- Only the English Red/Blue character map is in scope.
