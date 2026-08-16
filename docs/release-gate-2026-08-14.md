# Parser and progress repository release gate — 2026-08-14

## Outcome

The implemented parser, canonical world layer, rules slice, and filesystem
snapshot/history repository pass 84 automated
tests and forced compilation of every project module.

## Parser robustness exercised

- Golden Blue save and independently asserted parsed fields.
- Every one-byte mutation across the 3,979-byte main checksum region.
- 250 deterministic random full-size 32 KiB inputs.
- File sizes 0, 1, 32,767, 32,769, and 65,536 bytes.
- Main, PC-bank, and individual-box checksum failures.
- Counts, list terminators, species agreement, MissingNo, levels, and HP.
- Empty, unknown-character, and unterminated names.
- Invalid money BCD and item-list structure.
- Complete 151-species and 248-map registries with source provenance.
- Complete 165-move, 151-species base-data, and 16-defined-type registries
  generated from a pinned source revision with a combined source hash.
- Stored species types, move packing and IDs, PP/PP Ups, status exclusivity,
  experience thresholds, and calculated party stats.
- Player tile coordinates and map-bound validation.
- Pinned Red/Blue encounter, trainer, visible-item, hidden-item, and outdoor
  connection imports with per-record source references.
- Route 2 Red/Blue encounter differences, Super Rod tables, exact item tile
  coordinates, nearby-route guidance, next-trainer candidate data, and
  consumed-area rule notifications.
- Append-only encounter history transitions and guidance rebuilt from the last
  accepted snapshot.
- Missing-history versus explicitly unclaimed-area semantics, version-correct
  manual encounter choices, and rejection of impossible caught levels.
- Pewter's Boulder Badge gate, mandatory Gym objective, Jr. Trainer/Brock team
  sequence, level-14 cap, Route 3 lock, and active-party cap violations.
- Persistent event, toggleable-object, hidden-item, starter, and Hall of Fame
  offsets validated against the pinned disassembly and checksum-valid mutations.
- Automatic defeated-trainer removal, visible/hidden collection status, all
  eight Gym caps, all Elite Four caps, and starter-dependent Champion selection.
- Negative and zero-length binary reader boundaries.

## Snapshot repository behavior exercised

- Normalized JSON serialization and UTF-8 round-trip.
- Invalid saves cannot become snapshots or advance latest progress.
- Historical snapshots remain after latest advances.
- Duplicate snapshots are rejected.
- Registered run identity and version cannot be replaced by an injected
  snapshot.
- Snapshot schema and internal version consistency are enforced.
- Modification of the latest snapshot document is detected.
- Twenty concurrent uploads through one repository instance preserve all
  snapshot files and leave a readable latest snapshot.
- Three-player latest-progress summaries remain separate.

## Defects found and fixed

1. `SaveReader` silently accepted negative read sizes.
2. Runtime strings could bypass the `GameVersion` enum contract.
3. A snapshot with a different player/version could be appended to an existing
   run ID.
4. Concurrent latest-pointer replacement could fail on Windows.
5. Modified snapshot JSON was accepted without integrity detection.
6. Correctly terminated but empty in-game names were treated as valid.

Every defect now has a regression test.

The battle-normalization milestone also closes the earlier raw-field gap:
types, moves, PP, status, growth curves, stat experience, and derived party
stats are now normalized and mechanically cross-validated.

## Residual risks and missing evidence

These are not claimed as completed:

- Two Blue fixtures are available: one early-game golden save and one
  externally sourced completed-game regression save. The latter may be
  save-edited and is not independent proof of gameplay legitimacy.
- There is no real Red golden save yet.
- Initialized/populated PC boxes are tested synthetically, not with an
  independently observed real save.
- Move learnset legality and version-specific move availability are not yet
  evaluated.
- Version-specific compatibility evidence is not implemented; version remains
  declared run configuration.
- Encounter-area grouping beyond map identity is not implemented.
- Encounter history is now part of progress summaries; death, wipe, and
  save/history reconciliation are not yet implemented.
- Old/Good Rod availability still needs fishable-tile topology.
- The S.S. Anne rival battle has no independent persistent defeat bit and stays
  explicitly unknown; collision/warp pathfinding is still not implemented.
- The filesystem repository protects threads in one process only. It does not
  provide database transactions, authentication, authorization, remote
  hosting, or malicious-tamper resistance.

The highest-value next testing asset is a small real-save corpus covering Red,
mid/late Blue, populated switched PC boxes, statuses, fainted Pokémon, badges,
and varied inventory.
