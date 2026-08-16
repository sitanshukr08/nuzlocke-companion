# Save fixture provenance

## `pokemon_blue.sav`

Early-game Pokémon Blue save used as the primary golden fixture. Its parsed
in-game state has been used throughout parser development, but it still lacks
an independent human observation log for every asserted field.

## `pokemon_blue_completed_online.sav`

- SHA-256: `455b9f0e7a6f6831fad130421381723b1d38edcabfd94b58e0d0f8c0605d602d`
- Size: 32,768 bytes
- Added: 2026-08-14
- Origin: user-supplied file found online; original page and author are unknown
- Classification: external, untrusted, completed-game regression fixture

The file passes the strict Red/Blue SRAM validation and provides useful
late-game coverage: all badges, one Hall of Fame entry, a full level-100 party,
complete Pokédex flags, 456 set event bits, and 329 mapped defeated trainers.
It may have been modified with a save editor and is not treated as evidence of
a legitimate playthrough, a Nuzlocke run, encounter history, or field
correctness independent of the parser. Do not publish or redistribute it
without first establishing its original source and permission.
