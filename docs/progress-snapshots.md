# Run snapshots and shared progress

## Purpose

Friends should be able to see the latest save each player uploaded without
destroying historical state or implying that the website is synchronized live
with an emulator.

```text
Uploaded .sav
    -> strict parser validation
    -> normalized SaveState
    -> immutable ProgressSnapshot
    -> run's latest pointer
    -> friends progress summary
```

Every upload is an observation. It is not Nuzlocke history and it does not
automatically decide that a fainted Pokémon is permanently dead.

## Run profiles

A profile has a stable `run_id`, player-facing display name, and declared game
version. Initial profiles are expected to be:

| Run ID | Player | Version |
| --- | --- | --- |
| `piyush-red` | Piyush | Red |
| `sitanshu-blue` | Sitanshu | Blue |
| `dravi-blue` | Dravi | Blue |

The version is run configuration, not a claim extracted from the save.

## Snapshot properties

Each accepted snapshot contains:

- schema version;
- stable snapshot UUID;
- run and player identity;
- UTC upload time;
- SHA-256 of the exact uploaded save;
- normalized trainer, location, party, PC, badges, inventory, and Pokédex;
- parser diagnostics and byte provenance.

The filesystem adapter writes snapshots immutably. A duplicate ID is rejected,
and advancing `latest.json` never deletes an older snapshot. An invalid upload
does not change the latest pointer. The latest pointer records a SHA-256 of the
serialized snapshot document so accidental modification or partial corruption
is detected while reading. This checksum provides integrity detection, not
authentication against an attacker who can rewrite both files.

## Friends summary

`list_latest_progress()` returns one latest observation per run with:

- player and declared version;
- last upload time;
- in-game trainer name and ID;
- normalized current location;
- badges;
- party species, nicknames, levels, observed HP, canonical types and moves,
  current/max PP, PP Ups, major status, and experience to the next level;
- number of observed PC Pokémon.

The response uses `nuzlocke_history_status: tracked` once append-only encounter
events exist for a run and includes the latest state for each claimed area.
It remains `not_evaluated` for runs without encounter history. Death, wipe, and
save/history reconciliation are still intentionally not claimed.

Encounter history is stored separately from save snapshots. A first encounter
may transition from `encountered` to one terminal outcome (`caught`, `missed`,
`fled`, or `fainted`), but a terminal area cannot be reopened. These events are
user-declared because the Gen I save does not record which wild battle was the
first encounter under Nuzlocke rules.

Manual records preserve area, wild method, species, encountered/caught level,
nickname, outcome, and source category (`wild`, `gift`, `static`, or `trade`).
Wild entries are checked against the selected run version's canonical area
table, so an impossible species, method, or level is rejected before storage.

## Persistence boundary

`FileSnapshotRepository` is a development/small-group adapter with the same
conceptual boundary a database-backed web service will use:

```python
snapshot = repository.upload_save(profile, save_bytes)
friends = repository.list_latest_progress()
```

For public or internet-facing deployment, replace the filesystem adapter with
a transactional database implementation and add authenticated authorization:

- only a player or approved group member may upload to a run;
- group members may read latest summaries;
- original save bytes should be encrypted or deliberately discarded according
  to the chosen retention policy;
- snapshot metadata and run history remain immutable/auditable;
- upload size and rate limits are enforced before parsing.

The current adapter deliberately does not pretend to provide authentication,
multi-process transactions, remote hosting, or a browser UI. Operations through
one repository instance are protected against concurrent threads; a database
adapter remains required for multiple server processes.
