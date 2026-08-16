"""SQLite persistence and username/password authentication for shared runs."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from gen1_save_parser import GameVersion

from .progress import (
    SCHEMA_VERSION,
    FileSnapshotRepository,
    ProgressSnapshot,
    RepositoryCorruptionError,
    RunProfile,
    _iso_utc,
    _snapshot_identity_is_valid,
    create_snapshot,
    progress_summary,
)


USERNAME = re.compile(r"^[a-z0-9][a-z0-9_]{2,19}$")
SESSION_DAYS = 30


@dataclass(frozen=True)
class AccountAccess:
    username: str
    session_token: str
    account_created: bool


def normalize_username(value: str) -> str:
    username = value.strip().casefold()
    if not USERNAME.fullmatch(username):
        raise ValueError("username must be 3–20 characters using lowercase letters, numbers, or underscores")
    return username


def _validate_password(value: str) -> None:
    if len(value) < 8:
        raise ValueError("password must contain at least 8 characters")
    if len(value) > 128:
        raise ValueError("password must contain no more than 128 characters")


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)


class SQLiteSnapshotRepository:
    """Transactional run storage with public usernames and private owner sessions."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "nuzlocke.sqlite3"
        self._lock = threading.RLock()
        self._initialize()
        self._migrate_legacy_files()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as db:
            db.executescript("""
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    player_display_name TEXT NOT NULL,
                    game_version TEXT NOT NULL CHECK (game_version IN ('red', 'blue')),
                    username TEXT UNIQUE,
                    password_salt BLOB,
                    password_hash BLOB,
                    created_at TEXT NOT NULL,
                    CHECK ((username IS NULL AND password_salt IS NULL AND password_hash IS NULL)
                        OR (username IS NOT NULL AND password_salt IS NOT NULL AND password_hash IS NOT NULL))
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    session_hash TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_run_id ON sessions(run_id);
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    uploaded_at TEXT NOT NULL,
                    save_sha256 TEXT NOT NULL,
                    document_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS snapshots_run_time ON snapshots(run_id, uploaded_at, snapshot_id);
                CREATE TABLE IF NOT EXISTS latest_snapshots (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
                    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id)
                );
                CREATE TABLE IF NOT EXISTS encounter_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    recorded_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    UNIQUE(run_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS shared_dashboards (
                    run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
                    snapshot_id TEXT NOT NULL,
                    dashboard_json TEXT NOT NULL,
                    published_at TEXT NOT NULL
                );
            """)

    def _migrate_legacy_files(self) -> None:
        """Import the old append-only JSON repository once, preserving every usable fact."""
        runs_root = self.root / "runs"
        if not runs_root.exists():
            return
        with self._lock, self._connection() as db:
            if db.execute("SELECT 1 FROM metadata WHERE key='legacy_json_import_v1'").fetchone():
                return
            for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
                try:
                    profile = json.loads((run_dir / "profile.json").read_text(encoding="utf-8"))
                    run_id = str(profile["run_id"])
                    display_name = str(profile["player_display_name"])
                    version = GameVersion(str(profile["game_version"])).value
                except (KeyError, OSError, UnicodeError, json.JSONDecodeError, ValueError):
                    continue
                db.execute(
                    "INSERT OR IGNORE INTO runs(run_id, player_display_name, game_version, created_at) VALUES(?,?,?,?)",
                    (run_id, display_name, version, _iso_utc(None)),
                )
                snapshot_ids: set[str] = set()
                snapshots_dir = run_dir / "snapshots"
                for path in snapshots_dir.glob("*.json") if snapshots_dir.exists() else ():
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                        snapshot = ProgressSnapshot(**payload)
                        if snapshot.run_id != run_id or path.stem != snapshot.snapshot_id or not _snapshot_identity_is_valid(snapshot):
                            continue
                        db.execute(
                            "INSERT OR IGNORE INTO snapshots(snapshot_id,run_id,uploaded_at,save_sha256,document_json) VALUES(?,?,?,?,?)",
                            (snapshot.snapshot_id, run_id, snapshot.uploaded_at, snapshot.save_sha256, json.dumps(payload, ensure_ascii=False)),
                        )
                        snapshot_ids.add(snapshot.snapshot_id)
                    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                        continue
                latest_id = None
                try:
                    latest_id = json.loads((run_dir / "latest.json").read_text(encoding="utf-8"))["snapshot_id"]
                except (KeyError, OSError, UnicodeError, json.JSONDecodeError, TypeError):
                    pass
                if latest_id not in snapshot_ids and snapshot_ids:
                    latest_id = db.execute(
                        "SELECT snapshot_id FROM snapshots WHERE run_id=? ORDER BY uploaded_at DESC,snapshot_id DESC LIMIT 1", (run_id,),
                    ).fetchone()[0]
                if latest_id in snapshot_ids:
                    db.execute("INSERT OR REPLACE INTO latest_snapshots(run_id,snapshot_id) VALUES(?,?)", (run_id, latest_id))
                encounters_dir = run_dir / "history" / "encounters"
                for path in encounters_dir.glob("*.json") if encounters_dir.exists() else ():
                    try:
                        event = json.loads(path.read_text(encoding="utf-8"))
                        if event.get("run_id") != run_id or event.get("schema_version") != 1:
                            continue
                        db.execute(
                            "INSERT OR IGNORE INTO encounter_events(event_id,run_id,sequence,recorded_at,payload_json) VALUES(?,?,?,?,?)",
                            (event["event_id"], run_id, event["sequence"], event["recorded_at"], json.dumps(event, ensure_ascii=False)),
                        )
                    except (KeyError, OSError, UnicodeError, json.JSONDecodeError, sqlite3.IntegrityError, TypeError):
                        continue
                try:
                    shared = json.loads((run_dir / "shared" / "latest.json").read_text(encoding="utf-8"))
                    if shared.get("schema_version") == 1 and isinstance(shared.get("dashboard"), dict):
                        db.execute(
                            "INSERT OR REPLACE INTO shared_dashboards(run_id,snapshot_id,dashboard_json,published_at) VALUES(?,?,?,?)",
                            (run_id, str(shared.get("snapshot_id", "")), json.dumps(shared["dashboard"], ensure_ascii=False), _iso_utc(None)),
                        )
                except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
                    pass
            db.execute("INSERT INTO metadata(key,value) VALUES('legacy_json_import_v1',?)", (_iso_utc(None),))

    def register_profile(self, profile: RunProfile) -> None:
        with self._lock, self._connection() as db:
            row = db.execute("SELECT player_display_name,game_version FROM runs WHERE run_id=?", (profile.run_id,)).fetchone()
            if row:
                if row["player_display_name"] != profile.player_display_name or row["game_version"] != profile.game_version.value:
                    raise ValueError(f"Run profile {profile.run_id!r} already exists with different data")
                return
            db.execute(
                "INSERT INTO runs(run_id,player_display_name,game_version,created_at) VALUES(?,?,?,?)",
                (profile.run_id, profile.player_display_name, profile.game_version.value, _iso_utc(None)),
            )

    def authenticate_or_claim(self, profile: RunProfile, username_value: str, password: str) -> AccountAccess:
        username = normalize_username(username_value)
        _validate_password(password)
        with self._lock, self._connection() as db:
            self.register_profile(profile)
            row = db.execute("SELECT username,password_salt,password_hash FROM runs WHERE run_id=?", (profile.run_id,)).fetchone()
            if row is None:
                raise ValueError("run profile disappeared during authentication")
            created = row["username"] is None
            if created:
                if db.execute("SELECT 1 FROM runs WHERE username=?", (username,)).fetchone():
                    raise ValueError("that username is already taken")
                salt = secrets.token_bytes(16)
                db.execute(
                    "UPDATE runs SET username=?,password_salt=?,password_hash=? WHERE run_id=? AND username IS NULL",
                    (username, salt, _password_hash(password, salt), profile.run_id),
                )
            else:
                if not secrets.compare_digest(str(row["username"]), username):
                    raise PermissionError("This save belongs to a different username.")
                actual = _password_hash(password, bytes(row["password_salt"]))
                if not secrets.compare_digest(actual, bytes(row["password_hash"])):
                    raise PermissionError("Incorrect password for this run.")
            token = secrets.token_urlsafe(32)
            expiry = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (_iso_utc(None),))
            db.execute(
                "INSERT INTO sessions(session_hash,run_id,expires_at) VALUES(?,?,?)",
                (hashlib.sha256(token.encode("utf-8")).hexdigest(), profile.run_id, _iso_utc(expiry)),
            )
            return AccountAccess(username, token, created)

    def authorize_session(self, run_id: str, token: str | None) -> None:
        if not token:
            raise PermissionError("Log in with the run username and password before making changes.")
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connection() as db:
            row = db.execute("SELECT run_id,expires_at FROM sessions WHERE session_hash=?", (digest,)).fetchone()
            if row is None or row["run_id"] != run_id or row["expires_at"] <= _iso_utc(None):
                raise PermissionError("Your login session has expired. Load the save and sign in again.")

    def username_for_run(self, run_id: str) -> str | None:
        with self._connection() as db:
            row = db.execute("SELECT username FROM runs WHERE run_id=?", (run_id,)).fetchone()
            return str(row[0]) if row and row[0] else None

    @staticmethod
    def _safe_dashboard(dashboard: dict[str, object]) -> dict[str, object]:
        safe = json.loads(json.dumps(dashboard, ensure_ascii=False))
        safe.pop("run_id", None)
        safe.pop("sharing", None)
        for entry in safe.get("run_history", {}).get("entries", []):
            entry.pop("save_sha256", None)
            entry.pop("snapshot_id", None)
        return safe

    def publish_shared_dashboard(self, run_id: str, snapshot_id: str, dashboard: dict[str, object]) -> None:
        safe = self._safe_dashboard(dashboard)
        with self._connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO shared_dashboards(run_id,snapshot_id,dashboard_json,published_at) VALUES(?,?,?,?)",
                (run_id, snapshot_id, json.dumps(safe, ensure_ascii=False), _iso_utc(None)),
            )

    def get_shared_dashboard(self, username_value: str) -> dict[str, object] | None:
        username = normalize_username(username_value)
        with self._connection() as db:
            row = db.execute(
                "SELECT s.dashboard_json FROM shared_dashboards s JOIN runs r ON r.run_id=s.run_id WHERE r.username=?", (username,),
            ).fetchone()
        if row is None:
            return None
        try:
            dashboard = json.loads(row[0])
            if not isinstance(dashboard, dict):
                raise TypeError("dashboard is not an object")
            dashboard["sharing"] = {"role": "viewer", "username": username, "viewer_path": f"/?user={username}"}
            return dashboard
        except (json.JSONDecodeError, TypeError) as exc:
            raise RepositoryCorruptionError(f"Shared view for {username!r} is corrupt: {exc}") from exc

    def append_snapshot(self, snapshot: ProgressSnapshot) -> None:
        if snapshot.schema_version != SCHEMA_VERSION or not _snapshot_identity_is_valid(snapshot):
            raise ValueError("invalid snapshot identity or schema")
        with self._lock, self._connection() as db:
            profile = db.execute("SELECT player_display_name,game_version FROM runs WHERE run_id=?", (snapshot.run_id,)).fetchone()
            if profile is None:
                raise ValueError(f"Run profile {snapshot.run_id!r} is not registered")
            if profile["player_display_name"] != snapshot.player_display_name or profile["game_version"] != snapshot.declared_game_version:
                raise ValueError("Snapshot identity/version does not match the registered run profile")
            try:
                db.execute(
                    "INSERT INTO snapshots(snapshot_id,run_id,uploaded_at,save_sha256,document_json) VALUES(?,?,?,?,?)",
                    (snapshot.snapshot_id, snapshot.run_id, snapshot.uploaded_at, snapshot.save_sha256, json.dumps(snapshot.to_dict(), ensure_ascii=False)),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Snapshot {snapshot.snapshot_id} already exists") from exc
            db.execute("INSERT OR REPLACE INTO latest_snapshots(run_id,snapshot_id) VALUES(?,?)", (snapshot.run_id, snapshot.snapshot_id))

    def upload_save(self, profile: RunProfile, save_bytes: bytes, *, uploaded_at: datetime | None = None) -> ProgressSnapshot:
        self.register_profile(profile)
        snapshot = create_snapshot(profile, save_bytes, uploaded_at=uploaded_at)
        self.append_snapshot(snapshot)
        return snapshot

    def append_encounter_event(self, run_id: str, record: object, *, recorded_at: datetime | None = None) -> str:
        from .rules import EncounterRecord, EncounterStatus, Ruleset, validate_encounter_record

        if not isinstance(record, EncounterRecord):
            raise TypeError("record must be an EncounterRecord")
        with self._lock:
            current = self.get_run_history(run_id).encounter_for_area(record.area_id)
            terminal = {EncounterStatus.CAUGHT, EncounterStatus.MISSED, EncounterStatus.FLED, EncounterStatus.FAINTED}
            if current and current.status in terminal:
                raise ValueError(f"Encounter area {record.area_id!r} is already terminal: {current.status.value}")
            if current and current.status is EncounterStatus.ENCOUNTERED and record.status is EncounterStatus.UNCLAIMED:
                raise ValueError(f"Encounter area {record.area_id!r} cannot return to unclaimed")
            if current and record.status is current.status:
                raise ValueError(f"Encounter area {record.area_id!r} is already {current.status.value}")
            if current and current.species_id and record.species_id and current.species_id != record.species_id:
                raise ValueError("encounter species cannot change during a status transition")
            effective = EncounterRecord(
                area_id=record.area_id, status=record.status,
                species_id=record.species_id if record.species_id is not None else (current.species_id if current else None),
                nickname=record.nickname if record.nickname is not None else (current.nickname if current else None),
                method=record.method if record.method is not None else (current.method if current else None),
                level=record.level if record.level is not None else (current.level if current else None),
                source=record.source if current is None or current.status is EncounterStatus.UNCLAIMED else current.source,
                notes=record.notes,
            )
            with self._connection() as db:
                profile = db.execute("SELECT game_version FROM runs WHERE run_id=?", (run_id,)).fetchone()
                if profile is None:
                    raise ValueError(f"Run profile {run_id!r} is not registered")
                validate_encounter_record(effective, GameVersion(profile[0]), ruleset=Ruleset())
                sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM encounter_events WHERE run_id=?", (run_id,)).fetchone()[0]
                event_id = str(uuid4())
                payload = {
                    "schema_version": 1, "event_id": event_id, "sequence": sequence, "run_id": run_id,
                    "recorded_at": _iso_utc(recorded_at), "area_id": record.area_id,
                    "status": effective.status.value, "species_id": effective.species_id,
                    "nickname": effective.nickname, "method": effective.method, "level": effective.level,
                    "encounter_source": effective.source.value, "notes": effective.notes,
                    "declaration_source": "user_declared",
                }
                db.execute(
                    "INSERT INTO encounter_events(event_id,run_id,sequence,recorded_at,payload_json) VALUES(?,?,?,?,?)",
                    (event_id, run_id, sequence, payload["recorded_at"], json.dumps(payload, ensure_ascii=False)),
                )
                return event_id

    def get_run_history(self, run_id: str) -> object:
        from .rules import EncounterRecord, EncounterSource, EncounterStatus, RunHistory

        with self._connection() as db:
            rows = db.execute("SELECT payload_json FROM encounter_events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
        latest: dict[str, EncounterRecord] = {}
        try:
            for row in rows:
                event = json.loads(row[0])
                latest[event["area_id"]] = EncounterRecord(
                    area_id=event["area_id"], status=EncounterStatus(event["status"]),
                    species_id=event.get("species_id"), nickname=event.get("nickname"),
                    method=event.get("method"), level=event.get("level"),
                    source=EncounterSource(event.get("encounter_source", "wild")), notes=event.get("notes"),
                )
            return RunHistory(encounters=tuple(latest[key] for key in sorted(latest)))
        except (KeyError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RepositoryCorruptionError(f"Encounter history for run {run_id!r} is corrupt: {exc}") from exc

    def get_latest_snapshot(self, run_id: str) -> ProgressSnapshot | None:
        with self._connection() as db:
            row = db.execute(
                "SELECT s.document_json FROM snapshots s JOIN latest_snapshots l ON l.snapshot_id=s.snapshot_id WHERE l.run_id=?", (run_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            snapshot = ProgressSnapshot(**json.loads(row[0]))
            if snapshot.run_id != run_id or not _snapshot_identity_is_valid(snapshot):
                raise ValueError("invalid snapshot identity")
            return snapshot
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RepositoryCorruptionError(f"Latest snapshot for run {run_id!r} is corrupt: {exc}") from exc

    def list_snapshots(self, run_id: str) -> list[ProgressSnapshot]:
        with self._connection() as db:
            rows = db.execute("SELECT document_json FROM snapshots WHERE run_id=? ORDER BY uploaded_at,snapshot_id", (run_id,)).fetchall()
        try:
            snapshots = [ProgressSnapshot(**json.loads(row[0])) for row in rows]
            if any(item.run_id != run_id or not _snapshot_identity_is_valid(item) for item in snapshots):
                raise ValueError("invalid snapshot identity")
            return snapshots
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RepositoryCorruptionError(f"Snapshot history for run {run_id!r} is corrupt: {exc}") from exc

    def get_latest_guidance(self, run_id: str) -> object | None:
        from .rules import build_location_guidance_from_snapshot
        latest = self.get_latest_snapshot(run_id)
        return build_location_guidance_from_snapshot(latest, self.get_run_history(run_id)) if latest else None

    def list_latest_progress(self) -> list[dict[str, object]]:
        with self._connection() as db:
            run_ids = [row[0] for row in db.execute("SELECT run_id FROM latest_snapshots ORDER BY run_id")]
        summaries = []
        for run_id in run_ids:
            latest = self.get_latest_snapshot(run_id)
            if latest is None:
                continue
            summary = progress_summary(latest)
            history = self.get_run_history(run_id)
            summary["nuzlocke_history_status"] = "tracked" if history.encounters else "not_evaluated"
            summaries.append(summary)
        return summaries
