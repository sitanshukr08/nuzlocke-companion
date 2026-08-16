"""Immutable save observations and shared latest-progress summaries."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from gen1_save_parser import GameVersion, parse_save_bytes
from gen1_save_parser.layout.gen1_species_index import get_species_name
from gen1_save_parser.models import SaveState


SCHEMA_VERSION = 1
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
VIEWER_CODE = re.compile(r"^[A-Z2-9]{8}$")
VIEWER_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class InvalidSaveError(ValueError):
    def __init__(self, state: SaveState):
        self.state = state
        codes = ", ".join(item.code for item in state.diagnostics) or "unknown_validation_failure"
        super().__init__(f"Save was not accepted: {codes}")


class RepositoryCorruptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunProfile:
    run_id: str
    player_display_name: str
    game_version: GameVersion

    def __post_init__(self) -> None:
        if not SAFE_ID.fullmatch(self.run_id):
            raise ValueError("run_id must use lowercase letters, numbers, underscores, or hyphens")
        if not self.player_display_name.strip():
            raise ValueError("player_display_name cannot be empty")
        if not isinstance(self.game_version, GameVersion):
            raise TypeError("game_version must be a GameVersion")


@dataclass(frozen=True)
class ProgressSnapshot:
    schema_version: int
    snapshot_id: str
    run_id: str
    player_display_name: str
    declared_game_version: str
    uploaded_at: str
    save_sha256: str
    save_state: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ShareAccess:
    viewer_code: str
    issued_owner_key: str | None = None


def _iso_utc(value: datetime | None) -> str:
    instant = value or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("uploaded_at must be timezone-aware")
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _provenance(value: object) -> dict[str, object]:
    return asdict(value)  # type: ignore[arg-type]


def _serialize_mon(mon: object) -> dict[str, object]:
    data = asdict(mon)  # type: ignore[arg-type]
    data["species_name"] = get_species_name(data["species_id"])  # type: ignore[arg-type]
    data["provenance"] = {
        key: _provenance(value)
        for key, value in getattr(mon, "provenance").items()
    }
    return data


def serialize_save_state(state: SaveState) -> dict[str, object]:
    return {
        "status": state.status.value,
        "trainer": {
            "name": state.player_name,
            "trainer_id": state.player_id,
            "rival_name": state.rival_name,
        },
        "game_version": state.game_version.value if state.game_version else None,
        "game_version_source": state.game_version_source,
        "location": {
            "raw_map_id": state.current_map_id,
            "location_id": state.location_id,
            "display_name": state.location_name,
            "player_x": state.player_x,
            "player_y": state.player_y,
        },
        "badges": {"raw": state.badges, "earned": list(state.earned_badges)},
        "world_state": {
            "player_starter_id": state.player_starter_id,
            "rival_starter_id": state.rival_starter_id,
            "hall_of_fame_team_count": state.hall_of_fame_team_count,
            "toggleable_object_flags": sorted(state.toggleable_object_flags),
            "obtained_hidden_item_flags": sorted(state.obtained_hidden_item_flags),
            "event_flags": sorted(state.event_flags),
        },
        "money": state.money,
        "party": [_serialize_mon(mon) for mon in state.party],
        "current_box_index": state.current_box_index,
        "boxes_initialized": state.boxes_initialized,
        "pc_boxes": [
            {
                "index": box.index,
                "status": box.status.value,
                "checksum_verified": box.checksum_verified,
                "members": [_serialize_mon(mon) for mon in box.members],
                "provenance": _provenance(box.provenance) if box.provenance else None,
            }
            for box in state.pc_boxes
        ],
        "inventory": {
            "bag": [asdict(item) for item in state.bag_items],
            "pc": [asdict(item) for item in state.pc_items],
        },
        "pokedex": {
            "owned": list(state.pokedex_owned),
            "seen": list(state.pokedex_seen),
        },
        "diagnostics": [
            {
                "code": item.code,
                "severity": item.severity.value,
                "message": item.message,
                "offset": item.offset,
                "details": item.details,
            }
            for item in state.diagnostics
        ],
        "provenance": {key: _provenance(value) for key, value in state.provenance.items()},
    }


def create_snapshot(
    profile: RunProfile,
    save_bytes: bytes,
    *,
    uploaded_at: datetime | None = None,
) -> ProgressSnapshot:
    state = parse_save_bytes(save_bytes, expected_version=profile.game_version)
    if not state.is_valid:
        raise InvalidSaveError(state)
    uploaded_at_text = _iso_utc(uploaded_at)
    save_hash = hashlib.sha256(save_bytes).hexdigest()
    snapshot_id = str(uuid5(NAMESPACE_URL, f"{profile.run_id}:{uploaded_at_text}:{save_hash}"))
    return ProgressSnapshot(
        schema_version=SCHEMA_VERSION,
        snapshot_id=snapshot_id,
        run_id=profile.run_id,
        player_display_name=profile.player_display_name,
        declared_game_version=profile.game_version.value,
        uploaded_at=uploaded_at_text,
        save_sha256=save_hash,
        save_state=serialize_save_state(state),
    )


def progress_summary(snapshot: ProgressSnapshot) -> dict[str, object]:
    state = snapshot.save_state
    party = state["party"]  # type: ignore[index]
    boxes = state["pc_boxes"]  # type: ignore[index]
    return {
        "run_id": snapshot.run_id,
        "player_display_name": snapshot.player_display_name,
        "game_version": snapshot.declared_game_version,
        "last_uploaded_at": snapshot.uploaded_at,
        "save_sha256": snapshot.save_sha256,
        "trainer": state["trainer"],  # type: ignore[index]
        "location": state["location"],  # type: ignore[index]
        "badges": state["badges"],  # type: ignore[index]
        "party": [
            {
                "species_id": mon["species_id"],
                "species_name": mon["species_name"],
                "nickname": mon["nickname"],
                "level": mon["level"],
                "current_hp": mon["current_hp"],
                "max_hp": mon["max_hp"],
                "types": mon["type_names"],
                "moves": mon["move_details"],
                "status_conditions": mon["status_conditions"],
                "experience_to_next_level": mon["experience_to_next_level"],
            }
            for mon in party  # type: ignore[union-attr]
        ],
        "observed_pc_pokemon": sum(len(box["members"]) for box in boxes),  # type: ignore[union-attr]
        "nuzlocke_history_status": "not_evaluated",
    }


def _snapshot_identity_is_valid(snapshot: ProgressSnapshot) -> bool:
    expected_id = str(uuid5(
        NAMESPACE_URL,
        f"{snapshot.run_id}:{snapshot.uploaded_at}:{snapshot.save_sha256}",
    ))
    return (
        snapshot.schema_version == SCHEMA_VERSION
        and snapshot.snapshot_id == expected_id
        and snapshot.save_state.get("game_version") == snapshot.declared_game_version
    )


def _party_signature(state: dict[str, object]) -> list[tuple[str, str, int]]:
    return [
        (str(mon["nickname"]), str(mon["species_name"]), int(mon["level"]))
        for mon in state.get("party", [])  # type: ignore[union-attr]
    ]


def _snapshot_changes(previous: ProgressSnapshot | None, current: ProgressSnapshot) -> list[str]:
    if previous is None:
        return ["First accepted save loaded for this run."]
    if previous.save_sha256 == current.save_sha256:
        return ["No save-data changes since the preceding load."]

    before, after = previous.save_state, current.save_state
    changes: list[str] = []
    before_location = before["location"]  # type: ignore[index]
    after_location = after["location"]  # type: ignore[index]
    before_place = (
        before_location["display_name"], before_location["player_x"], before_location["player_y"]
    )
    after_place = (
        after_location["display_name"], after_location["player_x"], after_location["player_y"]
    )
    if before_place != after_place:
        changes.append(
            f"Location: {before_place[0]} ({before_place[1]}, {before_place[2]}) → "
            f"{after_place[0]} ({after_place[1]}, {after_place[2]})."
        )

    old_badges = set(before["badges"]["earned"])  # type: ignore[index]
    new_badges = set(after["badges"]["earned"])  # type: ignore[index]
    earned = sorted(new_badges - old_badges)
    if earned:
        changes.append(f"Badge earned: {', '.join(earned)}.")

    old_party, new_party = _party_signature(before), _party_signature(after)
    for slot in range(max(len(old_party), len(new_party))):
        old = old_party[slot] if slot < len(old_party) else None
        new = new_party[slot] if slot < len(new_party) else None
        if old == new:
            continue
        if old is None and new is not None:
            changes.append(f"Party slot {slot + 1}: added {new[0]} ({new[1]}) L{new[2]}.")
        elif new is None and old is not None:
            changes.append(f"Party slot {slot + 1}: removed {old[0]} ({old[1]}) L{old[2]}.")
        elif old is not None and new is not None:
            changes.append(
                f"Party slot {slot + 1}: {old[0]} ({old[1]}) L{old[2]} → "
                f"{new[0]} ({new[1]}) L{new[2]}."
            )

    old_pc = sum(len(box["members"]) for box in before["pc_boxes"])  # type: ignore[index]
    new_pc = sum(len(box["members"]) for box in after["pc_boxes"])  # type: ignore[index]
    if old_pc != new_pc:
        changes.append(f"Boxed Pokémon: {old_pc} → {new_pc}.")
    old_owned = len(before["pokedex"]["owned"])  # type: ignore[index]
    new_owned = len(after["pokedex"]["owned"])  # type: ignore[index]
    if old_owned != new_owned:
        changes.append(f"Pokédex owned: {old_owned} → {new_owned}.")
    if before["money"] != after["money"]:
        changes.append(f"Money: ¥{before['money']} → ¥{after['money']}.")
    return changes or ["Save data changed outside the summarized fields."]


def build_run_history(snapshots: list[ProgressSnapshot]) -> dict[str, object]:
    """Build an honest timeline of locally accepted save uploads."""
    ordered = sorted(snapshots, key=lambda item: (item.uploaded_at, item.snapshot_id))
    entries = []
    for index, snapshot in enumerate(ordered):
        state = snapshot.save_state
        location = state["location"]  # type: ignore[index]
        boxes = state["pc_boxes"]  # type: ignore[index]
        entries.append({
            "sequence": index + 1,
            "snapshot_id": snapshot.snapshot_id,
            "uploaded_at": snapshot.uploaded_at,
            "save_sha256": snapshot.save_sha256,
            "is_latest": index == len(ordered) - 1,
            "location": {
                "map_id": location["raw_map_id"],
                "name": location["display_name"],
                "x": location["player_x"],
                "y": location["player_y"],
            },
            "badges": list(state["badges"]["earned"]),  # type: ignore[index]
            "party": [
                {
                    "species_id": mon["species_id"],
                    "species_name": mon["species_name"],
                    "nickname": mon["nickname"],
                    "level": mon["level"],
                }
                for mon in state["party"]  # type: ignore[index]
            ],
            "boxed_pokemon": sum(len(box["members"]) for box in boxes),
            "pokedex_owned": len(state["pokedex"]["owned"]),  # type: ignore[index]
            "money": state["money"],
            "changes": _snapshot_changes(ordered[index - 1] if index else None, snapshot),
        })
    return {
        "time_basis": "local_server_upload_time_utc",
        "time_explanation": "Times record when this laptop accepted each save, not when events happened in-game.",
        "total_snapshots": len(entries),
        "entries": list(reversed(entries)),
    }


class FileSnapshotRepository:
    """Small-group JSON repository; replaceable by a database adapter later."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._lock = threading.RLock()

    def _run_dir(self, run_id: str) -> Path:
        if not SAFE_ID.fullmatch(run_id):
            raise ValueError("invalid run_id")
        return self.root / "runs" / run_id

    @staticmethod
    def _json_bytes(value: dict[str, object]) -> bytes:
        return (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")

    @classmethod
    def _atomic_json(cls, path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
        try:
            temporary.write_bytes(cls._json_bytes(value))
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def register_profile(self, profile: RunProfile) -> None:
        with self._lock:
            path = self._run_dir(profile.run_id) / "profile.json"
            value = {
                "run_id": profile.run_id,
                "player_display_name": profile.player_display_name,
                "game_version": profile.game_version.value,
            }
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
                if any(existing.get(key) != expected for key, expected in value.items()):
                    raise ValueError(f"Run profile {profile.run_id!r} already exists with different data")
                return
            self._atomic_json(path, value)

    @staticmethod
    def _owner_key_digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _new_viewer_code(self) -> str:
        used = set()
        runs_dir = self.root / "runs"
        for path in runs_dir.glob("*/profile.json") if runs_dir.exists() else ():
            try:
                value = json.loads(path.read_text(encoding="utf-8")).get("viewer_code")
                if isinstance(value, str):
                    used.add(value)
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
        for _ in range(100):
            candidate = "".join(secrets.choice(VIEWER_ALPHABET) for _ in range(8))
            if candidate not in used:
                return candidate
        raise RuntimeError("could not allocate a unique viewer code")

    def authorize_or_claim_owner(self, profile: RunProfile, owner_key: str | None) -> ShareAccess:
        """Authorize a write or issue the first owner key for an unclaimed run."""
        with self._lock:
            self.register_profile(profile)
            path = self._run_dir(profile.run_id) / "profile.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            digest = payload.get("owner_key_sha256")
            viewer_code = payload.get("viewer_code")
            if digest is None:
                issued = secrets.token_urlsafe(32)
                viewer_code = self._new_viewer_code()
                payload.update({
                    "sharing_version": 1,
                    "owner_key_sha256": self._owner_key_digest(issued),
                    "viewer_code": viewer_code,
                })
                self._atomic_json(path, payload)
                return ShareAccess(str(viewer_code), issued)
            if not isinstance(digest, str) or not isinstance(viewer_code, str):
                raise RepositoryCorruptionError(f"Sharing credentials for run {profile.run_id!r} are corrupt")
            if not owner_key or not secrets.compare_digest(digest, self._owner_key_digest(owner_key)):
                raise PermissionError("This run belongs to another owner key. Use its original player device or key.")
            return ShareAccess(viewer_code)

    def authorize_owner(self, run_id: str, owner_key: str | None) -> None:
        with self._lock:
            path = self._run_dir(run_id) / "profile.json"
            if not path.exists():
                raise ValueError(f"Run profile {run_id!r} is not registered")
            payload = json.loads(path.read_text(encoding="utf-8"))
            digest = payload.get("owner_key_sha256")
            if not isinstance(digest, str) or not owner_key:
                raise PermissionError("An owner key is required for this change.")
            if not secrets.compare_digest(digest, self._owner_key_digest(owner_key)):
                raise PermissionError("The owner key is not valid for this run.")

    @staticmethod
    def normalize_viewer_code(value: str) -> str:
        normalized = re.sub(r"[^A-Z0-9]", "", value.upper())
        if not VIEWER_CODE.fullmatch(normalized):
            raise ValueError("viewer code must contain eight letters or digits")
        return normalized

    def _run_id_for_viewer_code(self, viewer_code: str) -> str | None:
        normalized = self.normalize_viewer_code(viewer_code)
        runs_dir = self.root / "runs"
        for path in runs_dir.glob("*/profile.json") if runs_dir.exists() else ():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("viewer_code") == normalized:
                    return str(payload["run_id"])
            except (KeyError, OSError, UnicodeError, json.JSONDecodeError, TypeError):
                continue
        return None

    def publish_shared_dashboard(self, run_id: str, snapshot_id: str, dashboard: dict[str, object]) -> None:
        """Publish a sanitized read-only projection; raw save bytes are never included."""
        with self._lock:
            safe = json.loads(json.dumps(dashboard, ensure_ascii=False))
            safe.pop("run_id", None)
            safe.pop("sharing", None)
            for entry in safe.get("run_history", {}).get("entries", []):
                entry.pop("save_sha256", None)
                entry.pop("snapshot_id", None)
            self._atomic_json(self._run_dir(run_id) / "shared" / "latest.json", {
                "schema_version": 1,
                "snapshot_id": snapshot_id,
                "dashboard": safe,
            })

    def get_shared_dashboard(self, viewer_code: str) -> dict[str, object] | None:
        with self._lock:
            normalized = self.normalize_viewer_code(viewer_code)
            run_id = self._run_id_for_viewer_code(normalized)
            if run_id is None:
                return None
            path = self._run_dir(run_id) / "shared" / "latest.json"
            if not path.exists():
                return None
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("schema_version") != 1 or not isinstance(payload.get("dashboard"), dict):
                    raise ValueError("invalid shared dashboard schema")
                dashboard = payload["dashboard"]
                dashboard["sharing"] = {"role": "viewer", "viewer_code": normalized}
                return dashboard
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise RepositoryCorruptionError(f"Shared view for code {normalized!r} is corrupt: {exc}") from exc

    def append_snapshot(self, snapshot: ProgressSnapshot) -> None:
        with self._lock:
            run_dir = self._run_dir(snapshot.run_id)
            profile_path = run_dir / "profile.json"
            if not profile_path.exists():
                raise ValueError(f"Run profile {snapshot.run_id!r} is not registered")
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            if (
                profile.get("run_id") != snapshot.run_id
                or profile.get("player_display_name") != snapshot.player_display_name
                or profile.get("game_version") != snapshot.declared_game_version
            ):
                raise ValueError("Snapshot identity/version does not match the registered run profile")
            if snapshot.schema_version != SCHEMA_VERSION:
                raise ValueError(f"Unsupported snapshot schema version {snapshot.schema_version}")
            if snapshot.save_state.get("game_version") != snapshot.declared_game_version:
                raise ValueError("Snapshot save-state version does not match its declared version")

            snapshot_path = run_dir / "snapshots" / f"{snapshot.snapshot_id}.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            payload = snapshot.to_dict()
            document = self._json_bytes(payload)
            document_hash = hashlib.sha256(document).hexdigest()
            temporary = snapshot_path.with_name(f".{snapshot_path.name}.{uuid4()}.tmp")
            try:
                with temporary.open("xb") as file:
                    file.write(document)
                    file.flush()
                    os.fsync(file.fileno())
                os.link(temporary, snapshot_path)
            except FileExistsError as exc:
                raise ValueError(f"Snapshot {snapshot.snapshot_id} already exists") from exc
            finally:
                temporary.unlink(missing_ok=True)
            self._atomic_json(run_dir / "latest.json", {
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_document_sha256": document_hash,
            })

    def upload_save(
        self,
        profile: RunProfile,
        save_bytes: bytes,
        *,
        uploaded_at: datetime | None = None,
    ) -> ProgressSnapshot:
        """Validate, snapshot, persist, and advance this run's latest pointer."""
        self.register_profile(profile)
        snapshot = create_snapshot(profile, save_bytes, uploaded_at=uploaded_at)
        self.append_snapshot(snapshot)
        return snapshot

    def append_encounter_event(
        self,
        run_id: str,
        record: object,
        *,
        recorded_at: datetime | None = None,
    ) -> str:
        """Persist one append-only user-declared first-encounter state change."""
        from .rules import EncounterRecord, EncounterStatus, Ruleset, validate_encounter_record

        if not isinstance(record, EncounterRecord):
            raise TypeError("record must be an EncounterRecord")
        with self._lock:
            run_dir = self._run_dir(run_id)
            if not (run_dir / "profile.json").exists():
                raise ValueError(f"Run profile {run_id!r} is not registered")
            current = self.get_run_history(run_id).encounter_for_area(record.area_id)
            terminal = {
                EncounterStatus.CAUGHT, EncounterStatus.MISSED,
                EncounterStatus.FLED, EncounterStatus.FAINTED,
            }
            if current and current.status in terminal:
                raise ValueError(f"Encounter area {record.area_id!r} is already terminal: {current.status.value}")
            if current and current.status is EncounterStatus.ENCOUNTERED and record.status is EncounterStatus.UNCLAIMED:
                raise ValueError(f"Encounter area {record.area_id!r} cannot return to unclaimed")
            if current and record.status is current.status:
                raise ValueError(f"Encounter area {record.area_id!r} is already {current.status.value}")
            if current and current.species_id and record.species_id and current.species_id != record.species_id:
                raise ValueError("encounter species cannot change during a status transition")
            effective = EncounterRecord(
                area_id=record.area_id,
                status=record.status,
                species_id=record.species_id if record.species_id is not None else (current.species_id if current else None),
                nickname=record.nickname if record.nickname is not None else (current.nickname if current else None),
                method=record.method if record.method is not None else (current.method if current else None),
                level=record.level if record.level is not None else (current.level if current else None),
                source=(
                    record.source
                    if current is None or current.status is EncounterStatus.UNCLAIMED
                    else current.source
                ),
                notes=record.notes,
            )
            profile = json.loads((run_dir / "profile.json").read_text(encoding="utf-8"))
            validate_encounter_record(effective, GameVersion(profile["game_version"]), ruleset=Ruleset())
            event_id = str(uuid4())
            encounter_directory = run_dir / "history" / "encounters"
            existing_sequences = []
            for existing_path in encounter_directory.glob("*.json") if encounter_directory.exists() else ():
                existing_payload = json.loads(existing_path.read_text(encoding="utf-8"))
                existing_sequences.append(existing_payload["sequence"])
            payload = {
                "schema_version": 1,
                "event_id": event_id,
                "sequence": max(existing_sequences, default=0) + 1,
                "run_id": run_id,
                "recorded_at": _iso_utc(recorded_at),
                "area_id": record.area_id,
                "status": effective.status.value,
                "species_id": effective.species_id,
                "nickname": effective.nickname,
                "method": effective.method,
                "level": effective.level,
                "encounter_source": effective.source.value,
                "notes": effective.notes,
                "declaration_source": "user_declared",
            }
            path = run_dir / "history" / "encounters" / f"{event_id}.json"
            self._atomic_json(path, payload)
            return event_id

    def get_run_history(self, run_id: str) -> object:
        from .rules import EncounterRecord, EncounterSource, EncounterStatus, RunHistory

        with self._lock:
            directory = self._run_dir(run_id) / "history" / "encounters"
            if not directory.exists():
                return RunHistory()
            try:
                events = []
                for path in directory.glob("*.json"):
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if payload.get("schema_version") != 1 or payload.get("run_id") != run_id:
                        raise ValueError(f"invalid encounter event identity in {path.name}")
                    events.append(payload)
                sequences = [event["sequence"] for event in events]
                if any(not isinstance(value, int) or value < 1 for value in sequences) or len(sequences) != len(set(sequences)):
                    raise ValueError("invalid or duplicate encounter event sequence")
                events.sort(key=lambda event: event["sequence"])
                latest: dict[str, EncounterRecord] = {}
                for event in events:
                    latest[event["area_id"]] = EncounterRecord(
                        area_id=event["area_id"], status=EncounterStatus(event["status"]),
                        species_id=event.get("species_id"), nickname=event.get("nickname"),
                        method=event.get("method"), level=event.get("level"),
                        source=EncounterSource(event.get("encounter_source", "wild")),
                        notes=event.get("notes"),
                    )
                return RunHistory(encounters=tuple(latest[key] for key in sorted(latest)))
            except (KeyError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise RepositoryCorruptionError(f"Encounter history for run {run_id!r} is corrupt: {exc}") from exc

    def get_latest_snapshot(self, run_id: str) -> ProgressSnapshot | None:
        with self._lock:
            run_dir = self._run_dir(run_id)
            pointer = run_dir / "latest.json"
            if not pointer.exists():
                return None
            try:
                pointer_data = json.loads(pointer.read_text(encoding="utf-8"))
                snapshot_id = pointer_data["snapshot_id"]
                expected_hash = pointer_data["snapshot_document_sha256"]
                if not isinstance(snapshot_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", snapshot_id):
                    raise ValueError("invalid snapshot ID")
                path = run_dir / "snapshots" / f"{snapshot_id}.json"
                document = path.read_bytes()
                actual_hash = hashlib.sha256(document).hexdigest()
                if actual_hash != expected_hash:
                    raise ValueError("snapshot document checksum mismatch")
                snapshot = ProgressSnapshot(**json.loads(document.decode("utf-8")))
                if snapshot.run_id != run_id or snapshot.schema_version != SCHEMA_VERSION:
                    raise ValueError("snapshot identity or schema mismatch")
                return snapshot
            except (KeyError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise RepositoryCorruptionError(
                    f"Latest snapshot metadata for run {run_id!r} is corrupt: {exc}"
                ) from exc

    def list_snapshots(self, run_id: str) -> list[ProgressSnapshot]:
        """Return every immutable snapshot after validating its derived identity."""
        with self._lock:
            directory = self._run_dir(run_id) / "snapshots"
            if not directory.exists():
                return []
            try:
                snapshots = []
                for path in directory.glob("*.json"):
                    snapshot = ProgressSnapshot(**json.loads(path.read_text(encoding="utf-8")))
                    if (
                        snapshot.run_id != run_id
                        or path.stem != snapshot.snapshot_id
                        or not _snapshot_identity_is_valid(snapshot)
                    ):
                        raise ValueError(f"invalid snapshot identity in {path.name}")
                    snapshots.append(snapshot)
                return sorted(snapshots, key=lambda item: (item.uploaded_at, item.snapshot_id))
            except (KeyError, OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise RepositoryCorruptionError(
                    f"Snapshot history for run {run_id!r} is corrupt: {exc}"
                ) from exc

    def get_latest_guidance(self, run_id: str) -> object | None:
        """Return rule-aware world guidance for the run's last accepted save."""
        from .rules import build_location_guidance_from_snapshot

        latest = self.get_latest_snapshot(run_id)
        if latest is None:
            return None
        return build_location_guidance_from_snapshot(latest, self.get_run_history(run_id))

    def list_latest_progress(self) -> list[dict[str, object]]:
        runs_dir = self.root / "runs"
        if not runs_dir.exists():
            return []
        summaries = []
        for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
            latest = self.get_latest_snapshot(run_dir.name)
            if latest is not None:
                summary = progress_summary(latest)
                history = self.get_run_history(run_dir.name)
                summary["nuzlocke_history_status"] = "tracked" if history.encounters else "not_evaluated"
                summary["encounters"] = [
                    {
                        "area_id": record.area_id,
                        "status": record.status.value,
                        "species_id": record.species_id,
                        "nickname": record.nickname,
                        "method": record.method,
                        "level": record.level,
                        "source": record.source.value,
                    }
                    for record in history.encounters
                ]
                summaries.append(summary)
        return summaries
