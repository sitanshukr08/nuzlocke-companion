import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from gen1_save_parser import GameVersion
from nuzlocke_app import (
    FileSnapshotRepository,
    InvalidSaveError,
    RepositoryCorruptionError,
    RunProfile,
    create_snapshot,
)
from nuzlocke_app.progress import build_run_history


FIXTURE = Path(__file__).parent / "fixtures" / "pokemon_blue.sav"


class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.save_bytes = FIXTURE.read_bytes()
        cls.profile = RunProfile("sitanshu-blue", "Sitanshu", GameVersion.BLUE)

    def test_snapshot_contains_normalized_progress_and_hash(self) -> None:
        snapshot = create_snapshot(
            self.profile,
            self.save_bytes,
            uploaded_at=datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(snapshot.uploaded_at, "2026-08-14T10:00:00Z")
        self.assertEqual(len(snapshot.save_sha256), 64)
        self.assertEqual(snapshot.save_state["trainer"]["name"], "FLAMER")
        self.assertEqual(snapshot.save_state["location"]["location_id"], "pewter_city")
        self.assertEqual(snapshot.save_state["party"][1]["nickname"], "Keeda")
        self.assertEqual(snapshot.save_state["party"][1]["type_names"], ["Bug", "Flying"])
        self.assertEqual(snapshot.save_state["party"][2]["move_details"][2]["display_name"], "Ember")

    def test_invalid_save_never_becomes_snapshot(self) -> None:
        damaged = bytearray(self.save_bytes)
        damaged[0x2598] ^= 1
        with self.assertRaises(InvalidSaveError):
            create_snapshot(self.profile, bytes(damaged))

    def test_profile_requires_runtime_game_version_enum(self) -> None:
        with self.assertRaises(TypeError):
            RunProfile("bad-version", "Player", "blue")


class SharedProgressRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = FileSnapshotRepository(self.temporary.name)
        self.save_bytes = FIXTURE.read_bytes()

    def test_friends_view_returns_each_runs_latest_upload(self) -> None:
        profiles = [
            RunProfile("piyush-red", "Piyush", GameVersion.RED),
            RunProfile("sitanshu-blue", "Sitanshu", GameVersion.BLUE),
            RunProfile("dravi-blue", "Dravi", GameVersion.BLUE),
        ]
        for hour, profile in enumerate(profiles, start=10):
            self.repository.register_profile(profile)
            self.repository.append_snapshot(create_snapshot(
                profile,
                self.save_bytes,
                uploaded_at=datetime(2026, 8, 14, hour, 0, tzinfo=timezone.utc),
            ))

        summaries = self.repository.list_latest_progress()
        self.assertEqual([item["player_display_name"] for item in summaries], ["Dravi", "Piyush", "Sitanshu"])
        sitanshu = next(item for item in summaries if item["run_id"] == "sitanshu-blue")
        self.assertEqual(sitanshu["location"]["display_name"], "Pewter City")
        self.assertEqual(sitanshu["party"][2]["nickname"], "RealFlamer")
        self.assertEqual(sitanshu["party"][2]["types"], ["Fire", "Fire"])
        self.assertEqual(sitanshu["party"][2]["moves"][2]["display_name"], "Ember")
        self.assertEqual(sitanshu["party"][2]["experience_to_next_level"], 170)
        self.assertEqual(sitanshu["nuzlocke_history_status"], "not_evaluated")

    def test_latest_pointer_advances_without_deleting_history(self) -> None:
        profile = RunProfile("sitanshu-blue", "Sitanshu", GameVersion.BLUE)
        self.repository.register_profile(profile)
        first = create_snapshot(
            profile,
            self.save_bytes,
            uploaded_at=datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc),
        )
        second = create_snapshot(
            profile,
            self.save_bytes,
            uploaded_at=datetime(2026, 8, 14, 11, 0, tzinfo=timezone.utc),
        )
        self.repository.append_snapshot(first)
        self.repository.append_snapshot(second)

        latest = self.repository.get_latest_snapshot(profile.run_id)
        self.assertEqual(latest.snapshot_id, second.snapshot_id)
        snapshot_files = list(
            (Path(self.temporary.name) / "runs" / profile.run_id / "snapshots").glob("*.json")
        )
        self.assertEqual(len(snapshot_files), 2)

        snapshots = self.repository.list_snapshots(profile.run_id)
        self.assertEqual([item.snapshot_id for item in snapshots], [first.snapshot_id, second.snapshot_id])
        history = build_run_history(snapshots)
        self.assertEqual(history["total_snapshots"], 2)
        self.assertEqual(history["entries"][0]["sequence"], 2)
        self.assertTrue(history["entries"][0]["is_latest"])
        self.assertEqual(
            history["entries"][0]["changes"],
            ["No save-data changes since the preceding load."],
        )
        self.assertEqual(
            history["entries"][1]["changes"],
            ["First accepted save loaded for this run."],
        )

    def test_snapshot_files_are_valid_utf8_json(self) -> None:
        profile = RunProfile("sitanshu-blue", "Sitanshu", GameVersion.BLUE)
        self.repository.register_profile(profile)
        snapshot = create_snapshot(profile, self.save_bytes)
        self.repository.append_snapshot(snapshot)
        path = (
            Path(self.temporary.name) / "runs" / profile.run_id /
            "snapshots" / f"{snapshot.snapshot_id}.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["save_state"]["party"][0]["species_name"], "Nidoran♀")

    def test_duplicate_snapshot_is_rejected_to_preserve_immutability(self) -> None:
        profile = RunProfile("sitanshu-blue", "Sitanshu", GameVersion.BLUE)
        self.repository.register_profile(profile)
        snapshot = create_snapshot(
            profile,
            self.save_bytes,
            uploaded_at=datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc),
        )
        self.repository.append_snapshot(snapshot)
        with self.assertRaises(ValueError):
            self.repository.append_snapshot(snapshot)

    def test_upload_save_is_the_safe_ingestion_boundary(self) -> None:
        profile = RunProfile("dravi-blue", "Dravi", GameVersion.BLUE)
        snapshot = self.repository.upload_save(profile, self.save_bytes)
        self.assertEqual(
            self.repository.get_latest_snapshot(profile.run_id).snapshot_id,
            snapshot.snapshot_id,
        )

    def test_viewer_code_is_read_only_and_owner_key_controls_writes(self) -> None:
        profile = RunProfile("shared-blue", "Player", GameVersion.BLUE)
        access = self.repository.authorize_or_claim_owner(profile, None)
        self.assertRegex(access.viewer_code, r"^[A-Z2-9]{8}$")
        self.assertGreater(len(access.issued_owner_key), 30)
        with self.assertRaises(PermissionError):
            self.repository.authorize_or_claim_owner(profile, "wrong-owner-key")
        existing = self.repository.authorize_or_claim_owner(profile, access.issued_owner_key)
        self.assertEqual(existing.viewer_code, access.viewer_code)
        self.assertIsNone(existing.issued_owner_key)

        snapshot = self.repository.upload_save(profile, self.save_bytes)
        self.repository.publish_shared_dashboard(profile.run_id, snapshot.snapshot_id, {
            "run_id": profile.run_id,
            "trainer": {"name": "FLAMER"},
            "sharing": {"owner_key": access.issued_owner_key},
            "run_history": {"entries": [{"snapshot_id": snapshot.snapshot_id, "save_sha256": snapshot.save_sha256}]},
        })
        shared = self.repository.get_shared_dashboard(access.viewer_code)
        self.assertEqual(shared["trainer"]["name"], "FLAMER")
        self.assertEqual(shared["sharing"], {"role": "viewer", "viewer_code": access.viewer_code})
        self.assertNotIn("run_id", shared)
        self.assertNotIn("save_sha256", json.dumps(shared))
        damaged = bytearray(self.save_bytes)
        damaged[0x2598] ^= 1
        with self.assertRaises(InvalidSaveError):
            self.repository.upload_save(profile, bytes(damaged))
        self.assertEqual(
            self.repository.get_latest_snapshot(profile.run_id).snapshot_id,
            snapshot.snapshot_id,
        )

    def test_cross_profile_snapshot_injection_is_rejected(self) -> None:
        registered = RunProfile("shared-run", "Sitanshu", GameVersion.BLUE)
        self.repository.register_profile(registered)
        injected = create_snapshot(
            RunProfile("shared-run", "Dravi", GameVersion.RED),
            self.save_bytes,
        )
        with self.assertRaises(ValueError):
            self.repository.append_snapshot(injected)
        self.assertIsNone(self.repository.get_latest_snapshot(registered.run_id))

    def test_snapshot_schema_and_internal_version_must_match(self) -> None:
        profile = RunProfile("sitanshu-blue", "Sitanshu", GameVersion.BLUE)
        self.repository.register_profile(profile)
        snapshot = create_snapshot(profile, self.save_bytes)
        with self.assertRaises(ValueError):
            self.repository.append_snapshot(replace(snapshot, schema_version=999))
        changed_state = dict(snapshot.save_state)
        changed_state["game_version"] = "red"
        with self.assertRaises(ValueError):
            self.repository.append_snapshot(replace(snapshot, save_state=changed_state))

    def test_concurrent_uploads_preserve_all_snapshots_and_readable_latest(self) -> None:
        profile = RunProfile("concurrent-blue", "Player", GameVersion.BLUE)
        self.repository.register_profile(profile)
        snapshots = [
            create_snapshot(
                profile,
                self.save_bytes,
                uploaded_at=datetime(2026, 8, 14, 10, 0, second, tzinfo=timezone.utc),
            )
            for second in range(20)
        ]
        errors = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(self.repository.append_snapshot, snapshot) for snapshot in snapshots]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:  # captured so the assertion reports every failure
                    errors.append(exc)
        self.assertEqual(errors, [])
        directory = Path(self.temporary.name) / "runs" / profile.run_id / "snapshots"
        self.assertEqual(len(list(directory.glob("*.json"))), 20)
        self.assertIn(
            self.repository.get_latest_snapshot(profile.run_id).snapshot_id,
            {snapshot.snapshot_id for snapshot in snapshots},
        )

    def test_modified_latest_snapshot_is_detected(self) -> None:
        profile = RunProfile("sitanshu-blue", "Sitanshu", GameVersion.BLUE)
        snapshot = self.repository.upload_save(profile, self.save_bytes)
        path = (
            Path(self.temporary.name) / "runs" / profile.run_id /
            "snapshots" / f"{snapshot.snapshot_id}.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["player_display_name"] = "Tampered"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(RepositoryCorruptionError):
            self.repository.get_latest_snapshot(profile.run_id)


if __name__ == "__main__":
    unittest.main()
