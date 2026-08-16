# Nuzlocke Companion

Save-backed Pokémon Red/Blue Nuzlocke tracking with a deterministic Gen I
parser, rule-aware progression guidance, and a read-only friend dashboard.

The project accepts a raw 32 KiB Generation I save, validates it before any
data is exposed, normalizes it into typed Python models, and publishes a
dashboard containing the party, PC boxes, inventory, badges, story events,
nearby encounters, item availability, trainer guidance, and run history.
Nuzlocke declarations that cannot be proven from a Gen I save remain manual and
explicitly labeled as user-confirmed.

> Pokémon, character names, sprites, and game data belong to their respective
> owners. This is an unofficial fan project. See
> nuzlocke_app/web/assets/README.md for visual-asset provenance.

## Backend overview

The backend is a Python standard-library HTTP service. A save upload follows
this pipeline:

~~~text
raw .sav bytes
    -> size/checksum/structure validation
    -> Red/Blue SaveState
    -> canonical party, box, inventory, event, and location models
    -> rule-aware world guidance
    -> immutable SQLite snapshot
    -> sanitized owner dashboard or read-only friend dashboard
~~~

The server never trusts browser-provided Pokémon facts. It parses the save,
checks cross-field invariants, and rejects invalid data before creating a
snapshot. Manual encounter history is a separate append-only stream because
Generation I does not store the first wild encounter's route, level, or
Nuzlocke outcome.

## Main capabilities

- Exact 32 KiB Red/Blue save-size and main checksum validation.
- Party and initialized PC-box parsing, including nicknames, levels, HP,
  types, moves, PP, status, experience, DVs, and calculated stats.
- Trainer name/ID, rival name, money, badges, Pokédex, bag, PC inventory,
  story events, defeated trainers, starter choice, and Hall of Fame parsing.
- Canonical Gen I species, move, type, item, trainer, encounter, and story
  data with version-aware Red/Blue guidance.
- Rule notifications for consumed encounters, collected items, badge gates,
  level caps, blocked progression, and the next known undefeated trainer.
- Manual encounter records with area, method, species, nickname, outcome, and
  caught level. Impossible species/method/level combinations are rejected.
- Immutable save snapshots and a run-history view showing changes between
  accepted uploads.
- Public usernames for friend viewing and private passwords for owner writes.
- SQLite persistence with a one-time importer for the older JSON repository.
- Read-only shared dashboards that exclude raw saves, password material,
  internal run IDs, snapshot IDs, and save hashes.

## Repository architecture

~~~text
gen1_save_parser/       Binary reader, checksums, models, Gen I layouts
nuzlocke_app/
  dashboard.py           Save + rules -> browser dashboard payload
  reference.py           Canonical encounters/items/world lookup
  rules.py               Nuzlocke history and progression rules
  progress.py            Snapshot models and legacy JSON adapter
  sqlite_repository.py   SQLite accounts, sessions, snapshots, history
  server.py              Threaded HTTP API and static-file server
  data/                  Pinned generated world and trainer data
  web/                   Browser dashboard, CSS, and visual assets
tests/                   Parser, rules, repository, and API regression tests
tools/                   Data import and generation utilities
docs/                    Save-format, world-data, and progress contracts
render.yaml              Free, ephemeral Render preview
render-persistent.yaml   Paid, persistent SQLite Render configuration
~~~

The dashboard is a projection layer: parser facts, rule interpretations, and
manual declarations remain distinguishable in both payload and UI. The server
uses a single-process threaded HTTP model. SQLite transactions protect shared
state, but the persistent-disk deployment must remain a single instance.

## Accounts and sharing

The first valid upload for an unclaimed run creates an account:

- Username: 3–20 lowercase letters, numbers, or underscores; public and unique.
- Password: 8–128 characters; private and used for owner operations.

Passwords are stored as salted, memory-hard scrypt hashes. Successful owner
uploads create a 30-day HttpOnly browser session. Friends do not receive a
password; they open /?user=<username> or enter the username in the viewer
form. Viewer requests are read-only and receive a sanitized latest dashboard.

There is currently no password-reset email flow. Owners must keep their
password. Before production use, add password recovery, login rate limiting,
audit logging, and a managed database backup policy.

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /healthz | Deployment health check; returns status ok. |
| POST | /api/inspect?version=red or blue | Validate a save, authenticate or claim the run, persist a snapshot, and return the owner dashboard. |
| GET | /api/view?username=id | Return the latest sanitized read-only dashboard. |
| POST | /api/encounters | Persist a validated manual encounter; requires the owner's session cookie. |

The inspect endpoint receives the save as application/octet-stream and owner
credentials in X-Run-Username and X-Run-Password. Raw save bytes are not
included in shared responses. Uploads are capped at 1 MiB before parsing even
though valid Red/Blue saves are exactly 32 KiB.

## Local development

Requirements: Python 3.11 or newer. Runtime dependencies are Python standard
library only.

~~~powershell
cd "C:\path\to\nuzlocke_companion"
python -m nuzlocke_app.server
~~~

Open http://127.0.0.1:8765. Select the exact game version and choose a raw sav
file. Keep the server process running while using the browser. Only one server
may own port 8765.

The default data root is .nuzlocke_data; override it with
NUZLOCKE_DATA_ROOT. The SQLite database is
.nuzlocke_data/nuzlocke.sqlite3. Existing JSON runs under
.nuzlocke_data/runs/ are imported once at SQLite initialization. Save files,
database files, logs, and emulator state are excluded by .gitignore.

## Testing

Run the complete suite from the repository root:

~~~powershell
python -m unittest discover -v
~~~

Tests cover golden saves, deliberate byte corruption, parser boundaries,
party/box invariants, move and stat normalization, item and trainer guidance,
encounter transitions, snapshot immutability, SQLite authentication, legacy
migration, viewer privacy, session-only writes, and the HTTP API.

GitHub Actions runs the same test command on pushes and pull requests. A change
is not ready to merge if parser validation, data provenance, or the full
regression suite is weakened.

## Render deployment

The committed render.yaml is a free preview. It runs one Python web service
and writes SQLite under /tmp/nuzlocke-data. Render's free filesystem is
ephemeral, so accounts, snapshots, and manual history may disappear after a
restart. This mode is suitable for demonstrating the UI, not permanent data.

render-persistent.yaml is the paid alternative. It attaches a persistent disk
at /var/data and sets NUZLOCKE_DATA_ROOT=/var/data. Use it as the Blueprint
file when durable SQLite storage is required. A future managed Postgres adapter
is the preferred free multi-user architecture.

To deploy the preview, push the repository to GitHub, create a Render
Blueprint from the main branch, keep the Blueprint path as render.yaml, and
apply the detected service. The service uses:

~~~text
build: python -m compileall -q gen1_save_parser nuzlocke_app
start: python -m nuzlocke_app.server
health: /healthz
host: 0.0.0.0
~~~

## Accuracy boundaries

- Game version is run configuration; the standalone save does not identify
  Red versus Blue authoritatively.
- The save has no first-encounter route, level, or outcome fields. Those values
  are manual and labeled user-confirmed.
- Pokémon nicknames and party moves are parsed from the save, not inferred from
  species learnsets.
- Pokédex ownership does not imply a Nuzlocke encounter claim.
- Item existence, collection flags, inventory ownership, and route access are
  separate concepts.
- Trainer recommendations use known placement, event bits, progression gates,
  and accessible-area data. Walking-path collision/pathfinding is not claimed.
- The inaccurate map panel is removed until every interior map has a verified
  asset and coordinate transform. Current location name and save coordinates
  remain available in the dashboard.

See docs/gen1-save-format.md, docs/world-guidance.md, and
docs/progress-snapshots.md for detailed contracts and evidence boundaries.

## Contributing

1. Add or update a focused regression test for behavior changes.
2. Preserve provenance when changing generated Pokémon Red/Blue data.
3. Run python -m unittest discover -v.
4. Document a new limitation instead of silently guessing.
5. Never commit sav files, .nuzlocke_data, passwords, database files, private
   run data, or unlicensed artwork.

Parser changes should document the verified save offset, checksum invariant, or
source revision they rely on. If a value cannot be proven from the save,
represent it as unknown or manual.

## License and third-party data

No project software license has been selected yet. Until one is added, do not
assume the source code is licensed for redistribution. Pokémon game data and
visual assets remain third-party material; review each asset's provenance and
terms before redistributing a public build.

