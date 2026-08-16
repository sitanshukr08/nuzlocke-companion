"""Generate pinned Red/Blue trainer moveset data from pret/pokered."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from gen1_save_parser.layout.gen1_battle_data import MOVES, SPECIES_BASE_DATA


COMMIT = "0cd19d3b877b7dc66d12c7050bed9a7f38154d4b"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    evos_path = args.source / "data/pokemon/evos_moves.asm"
    evos_text = evos_path.read_text(encoding="utf-8")
    move_ids = {move.stable_id.upper(): move.move_id for move in MOVES.values()}
    normalize = lambda value: re.sub(r"[^a-z0-9]", "", value.casefold())
    labels = re.findall(r"^(\w+EvosMoves):", evos_text, re.MULTILINE)
    label_by_species = {normalize(label.removesuffix("EvosMoves")): label for label in labels}

    sources = [evos_path]
    species_payload: dict[str, object] = {}
    for species in SPECIES_BASE_DATA.values():
        label = label_by_species[normalize(species.stable_id)]
        filename = {"nidoran_f": "nidoranf", "nidoran_m": "nidoranm", "mr_mime": "mrmime"}.get(
            species.stable_id, species.stable_id
        )
        base_path = args.source / "data/pokemon/base_stats" / f"{filename}.asm"
        sources.append(base_path)
        base_text = base_path.read_text(encoding="utf-8")
        starting_match = re.search(r"^\s*db\s+([^;]+);\s*level 1 learnset", base_text, re.MULTILINE)
        if not starting_match:
            raise ValueError(f"missing starting moves for {species.display_name}")
        starting_moves = [
            move_ids[symbol.strip()] for symbol in starting_match.group(1).split(",")
            if symbol.strip() != "NO_MOVE"
        ]

        block = evos_text.split(f"{label}:", 1)[1]
        block = re.split(r"^\w+EvosMoves:", block, maxsplit=1, flags=re.MULTILINE)[0]
        learnset_text = block.split("db 0", 1)[1]
        level_up = []
        for level, symbol in re.findall(r"^\s*db\s+(\d+)\s*,\s*(\w+)", learnset_text, re.MULTILINE):
            level_up.append([int(level), move_ids[symbol]])
        species_payload[str(species.internal_id)] = {
            "starting_moves": starting_moves,
            "level_up_moves": level_up,
        }

    digest = hashlib.sha256()
    for path in sources:
        digest.update(path.relative_to(args.source).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    payload = {
        "schema_version": 1,
        "source": "pret/pokered",
        "source_commit": COMMIT,
        "source_sha256": digest.hexdigest(),
        "trainer_dvs": {"hp": 8, "attack": 9, "defense": 8, "speed": 8, "special": 8},
        "trainer_stat_exp": [0, 0, 0, 0, 0],
        "species": species_payload,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
