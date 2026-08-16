# Contributing

Before opening a pull request:

1. Add a focused regression test for behavior changes.
2. Run python -m unittest discover -v from the repository root.
3. Preserve provenance when changing generated Pokémon Red/Blue data.
4. Keep parser facts, rules, persistence, and UI projection layers separate.
5. Do not include sav files, .nuzlocke_data, passwords, database files, or
   unlicensed assets.

Parser changes should document the verified save offset, checksum invariant,
or source revision they rely on. If a value cannot be proven from the save,
represent it as unknown or manual rather than guessing.

