# Canonical world data and rule-aware guidance

## Data source and coverage

`nuzlocke_app/data/gen1_world.json` is generated from `pret/pokered` commit
`0cd19d3b877b7dc66d12c7050bed9a7f38154d4b`. The combined imported-source
SHA-256 is `f55b8e48559cd4cdef790ada8c9ef70aa76673373a20618706e1c8e2a300f75c`.
Every record includes a source reference to the relevant disassembly table.

Current generated coverage:

- 1,378 version-scoped grass, Surf, and Super Rod slots;
- 674 trainer/team records (337 separately represented for Red and Blue),
  including the three starter-dependent Champion teams;
- 262 visible and hidden item placements, with exact tile coordinates;
- 78 outdoor map connections.

All 208 visible item balls and all 112 hidden-item slots are linked to their
persistent save flags. Of the 674 trainer/team records, 672 have a persistent
defeat event. The two version-scoped S.S. Anne rival records are explicitly
unknown because that scripted battle has no independent persistent defeat bit.

The source generator is `tools/import_pokered_world_data.py`. Application code
never scrapes a third-party page at runtime.

## Guidance contract

```python
guidance = build_location_guidance(parsed_save, run_history)
guidance = repository.get_latest_guidance(run_id)
```

The result contains current save location and player coordinates, connected
areas with version-correct encounter species/types/levels, item placements,
the next trainer candidate and party, deterministic rule notifications, source
provenance, and explicit limitations.

For the Blue golden fixture in Pewter City, the connected encounter areas are
Route 2 and Route 3. Because the save has no Boulder Badge, progression guidance
marks Route 3 inaccessible and selects Pewter Gym as the mandatory objective.
The next Gym trainer is Jr. Trainer♂ with Diglett Lv.11 and Sandshrew Lv.11;
Brock follows with Geodude Lv.12 and Onix Lv.14. Brock sets the active level cap
to 14, and an active party member above it produces `level_cap_exceeded`.

The save's trainer event flags are merged with manually recorded trainer
history before selection, so an already defeated trainer is skipped. During an
active boss milestone, undefeated mandatory Gym trainers precede the leader;
the system then advances through all eight Gyms, Lorelei, Bruno, Agatha, Lance,
and the starter-dependent Champion team. The active level caps are
14/21/24/29/43/43/47/50/56/58/60/62/65.

Outside mandatory progression, “next trainer” uses Manhattan
distance from parsed player coordinates. On a connected map it estimates
distance from the connecting edge. It does not yet claim collision-aware path
distance or player intent. Scripted rival encounters without a persistent bit
remain qualified rather than being guessed.

## Encounter rule history

The default limited-encounter rule treats `encountered`, `caught`, `missed`,
`fled`, and `fainted` as consuming the area's first encounter. For example, a
persisted `route_2: caught` record produces `area_encounter_consumed` and the
message that another Route 2 Pokémon must not be caught.

No history record means `unknown`, not available. The engine emits
`area_encounter_history_required` until the player explicitly records an area
as `unclaimed` or supplies its encounter result. This prevents an incomplete
history import from accidentally authorizing a second catch.

## Manual encounter entry

Gen I does not store caught location or caught level. The application therefore
provides canonical selection options rather than a free-form guess:

1. Select an area.
2. Select `wild`, `gift`, `static`, or `trade` as the source.
3. For a wild encounter, select a method and species from that area's
   version-correct encounter table.
4. Select a level from the exact levels valid for that species/method.
5. Select the outcome and enter the nickname when caught.

`validate_encounter_record()` rejects impossible wild species, methods, and
levels. `append_encounter_event()` stores the validated result append-only and
allows an `encountered` event to inherit its details when it later transitions
to `caught`, `missed`, `fled`, or `fainted`.

Pokédex seen/owned flags are deliberately not used as encounter history. They
cannot prove where or under which Nuzlocke circumstances a Pokémon was met.
Encounter events are append-only, user-declared facts stored separately from
immutable save snapshots.

## Item interpretation

Visible Poké Ball objects and hidden-item events have exact map tile `(x, y)`
coordinates. Each returned item now includes `collected: true/false`, decoded
from `wToggleableObjectFlags` or `wObtainedHiddenItemsFlags`. Inaccessible
source entries are retained and explicitly marked rather than silently
presented as available.
Shop inventories, NPC gifts, and battle rewards are separate systems and are
not yet included in `items_here`.

Human walkthrough prose and screenshots may later be attached as corroborating
references, but the canonical coordinates and item identities come directly
from game data to avoid page-layout scraping and ambiguous directions.

## Remaining work

- import Old/Good Rod encounters after exact fishable-tile topology is modeled;
- group indoor maps/floors into configurable Nuzlocke encounter areas;
- add collision/warp-aware pathfinding before labeling a trainer strictly
  “next” without qualification;
- expand route blocking from the current badge/story gates to full key-item,
  one-way-warp, and tile-collision reachability;
- add deaths, wipes, and save/history reconciliation.
