# Nuzlocke Companion

## Accounts and shared runs

The first valid save load creates one account for that run:

- A unique 3–20 character username is the public run ID friends use to view progress.
- A private password authorizes save uploads and creates a 30-day browser session for manual changes.

Passwords are processed with Python's memory-hard `scrypt` function and a random per-account
salt; plaintext passwords are never stored. Shared payloads never contain raw save bytes,
password data, run IDs, snapshot IDs, or save hashes.

Viewer URLs use `/?user=username`. Spectators can inspect the party, PC boxes, encounters,
trainers, items, map, badges, and run history but cannot modify the run.

All profiles, password hashes, login sessions, immutable snapshots, manual encounter events,
and published dashboards are stored transactionally in `.nuzlocke_data/nuzlocke.sqlite3`.
On first startup, the app imports the previous `.nuzlocke_data/runs/...` JSON repository into
SQLite once, preserving run history; a valid save upload then claims an imported run with its
new username and password.

## Public deployment

The included `render.yaml` defines a single-instance Python web service with a persistent disk.
Persistence is required: an ephemeral filesystem would lose accounts, snapshots, manual
encounters, and snapshot history whenever the service restarts.

The service reads these environment variables:

- `HOST` (production value `0.0.0.0`)
- `PORT` (provided by the hosting platform)
- `NUZLOCKE_DATA_ROOT` (persistent mount path, `/var/data` in the Blueprint)

`GET /healthz` is the deployment health check. Never commit `.nuzlocke_data` or emulator save
files; both are excluded by `.gitignore`.

Trustworthy Pokémon Red/Blue save parsing is the first development milestone.
The local web dashboard, canonical game database, Nuzlocke history, and rules
engine are built on top of this deterministic core.

## Run the GBC dashboard

From the repository root with Python 3.11 or newer:

```powershell
python -m nuzlocke_app.server
```

Then open `http://127.0.0.1:8765`, select Pokémon Red or Blue, and choose a
32 KiB `.sav` file. The browser sends the bytes only to this local Python
process. The dashboard renders the parsed trainer name and Pokémon nicknames,
party/moves/levels, location, badges, active boss and cap, next undefeated
trainer, nearby version-correct encounters, route locks, and remaining mapped
items. Dedicated Party, Items, and Kanto Map screens use the live save state;
the Items screen decodes canonical names and quantities from both the counted
bag list and PC item list while keeping those entries distinct from world
placements. The Town Map marker uses Red/Blue's original coordinate-to-OAM
calculation instead of a generic percentage approximation. Original
Red/Blue character sprites replace placeholder portraits. Item existence,
collection state, and current reachability are kept separate. For example,
Route 2's HP Up and Moon Stone remain locked until Cut is usable instead of
being presented as immediately obtainable. Unmodeled walking-path requirements
are explicitly marked unverified. Encounter history remains explicitly unknown
until the player records it manually; Pokédex ownership is not used to invent a
route claim.

Keep the PowerShell server window open while using the dashboard. Only one
server instance may own port 8765; a second launch now exits with a clear
message instead of silently competing for browser requests. If the page says
it cannot reach the local server, stop any old instance with `Ctrl+C`, start
the command once, and reload the page.

The active Gym/League milestone supplies the progression gate and level cap,
but it no longer overrides the trainer recommendation. The dashboard selects
the nearest undefeated trainer on the current map, then on an accessible
directly connected map, and falls back to the active milestone trainer only
when no local reachable candidate is known.

Scripted encounters that are not ordinary map-object trainers are added
explicitly when their save events and teams are known. In Cerulean City, the
unbeaten starter-dependent rival battle is recommended before Nugget Bridge;
the Rocket thief is excluded until Bill's S.S. Ticket event makes that part of
the city reachable.

## Current parser capabilities

- validates exact 32 KiB save size;
- validates the main saved-data checksum;
- validates party/current-box counts, terminators, species agreement, real
  species IDs, levels, and party HP consistency;
- parses the party and current-box cache;
- parses the player's in-game trainer name and ID, separately from Pokémon
  nicknames and original-trainer names;
- parses rival name, money, bag/PC items, Pokédex seen/owned state, and badges;
- parses persistent trainer/story events, visible/hidden item collection flags,
  starters, and Hall of Fame completion;
- parses all twelve persistent PC boxes after they have been initialized and
  verifies both whole-bank and individual-box checksums;
- represents untouched PC banks as unknown/uninitialized instead of empty;
- decodes English Gen I names;
- records byte-level provenance for important fields;
- returns structured status and diagnostics;
- maps all 151 real Pokémon from Gen I internal IDs;
- normalizes all 165 Gen I moves, the 16 defined type IDs, PP/PP Ups,
  major status conditions, experience progress, and species base data;
- cross-validates stored types, move slots, PP limits, experience/level ranges,
  and calculated party stats before exposing a save;
- includes golden-fixture and deliberate-corruption tests.

## Location-aware Nuzlocke guidance

The canonical world layer now contains version-specific grass, Surf, and
Super Rod encounters; trainer placements and parties; visible and hidden item
tile coordinates; and outdoor map connections. `build_location_guidance()`
combines that data with a parsed save and append-only user-maintained encounter
history to report nearby encounter areas, Pokémon types/levels, an explicitly
qualified next-trainer candidate, item placements, and rule notifications.
Progression now advances through every Gym, all four Elite Four members, and
the correct starter-dependent Champion team. Save event bits remove defeated
trainers and collected items automatically; badge/event milestones update the
active cap and route-access warnings. At Pewter, this selects the remaining Gym
trainer or Brock, applies cap 14, and keeps Route 3 blocked until Boulder.

Trainer Pokémon include their exact Red/Blue generated movesets and battle
stats. The calculation uses the game's fixed trainer DVs (Attack 9; Defense,
Speed, and Special 8), zero stat experience, level-up move replacement rules,
and the special Gym Leader, Elite Four, and Champion move overrides. In the
Trainer Guide, selecting any Pokémon opens its HP, Attack, Defense, Speed,
Special, types, moves, power, accuracy, PP, and physical/special category.

`encounter_choices(area_id, version)` supplies safe manual-entry choices for
area, method, species, and valid encounter levels. Persisted caught records
also store the user-confirmed caught level, nickname, and encounter source.

The web dashboard now assigns each loaded save a stable run ID and persists
validated encounter events under `.nuzlocke_data/runs/<run-id>/history`.
Reloading the same save restores those records and immediately reapplies
first-encounter availability warnings. Terminal results (`caught`, `missed`,
`fled`, and `fainted`) are append-only audit facts and cannot be silently
overwritten from the interface.

Party cards link caught records by nickname first (so the link survives
evolution), with a unique-species fallback. The displayed caught level and
route are explicitly labeled as user-confirmed because Red/Blue party data
does not contain met-location or met-level fields.

The filesystem repository persists encounter state transitions and can rebuild
guidance from the last accepted snapshot with `get_latest_guidance(run_id)`.
See [world data and rule-aware guidance](docs/world-guidance.md).

See [the save-format specification](docs/gen1-save-format.md) for verified
offsets, sources, invariants, and explicit limitations.

## Run the tests

From the repository root with Python 3.11 or newer:

```powershell
python -m unittest discover -v
```

The project currently uses only the Python standard library.

## Shared progress foundation

The application layer now supports immutable per-run save snapshots and a
latest-progress summary for the three players. See
[run snapshots and shared progress](docs/progress-snapshots.md) for the data
contract, limitations, and future authenticated web boundary.

## Public parser API

```python
from gen1_save_parser import GameVersion, parse_save, parse_save_bytes, validate_save_bytes

validation = validate_save_bytes(uploaded_bytes)
state = parse_save_bytes(uploaded_bytes, expected_version=GameVersion.BLUE)
state_from_path = parse_save("run.sav", expected_version=GameVersion.BLUE)
```

Callers must check `state.status` or `state.is_valid` before using parsed data.
Invalid input is never returned as a partially trusted party or box state.
The expected Red/Blue version comes from the run configuration because the
standalone save does not contain an authoritative version header.
