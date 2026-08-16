from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from gen1_save_parser import GameVersion, parse_save_bytes
from nuzlocke_app.progress import FileSnapshotRepository, RunProfile
from nuzlocke_app.server import NuzlockeHTTPServer, NuzlockeRequestHandler
from nuzlocke_app.sqlite_repository import SQLiteSnapshotRepository


FIXTURE = Path(__file__).parent / "fixtures" / "pokemon_blue.sav"


class SQLiteRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = SQLiteSnapshotRepository(self.temporary.name)
        self.save_bytes = FIXTURE.read_bytes()
        state = parse_save_bytes(self.save_bytes, expected_version=GameVersion.BLUE)
        self.profile = RunProfile("blue-flamer-36591", state.player_name, GameVersion.BLUE)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_account_password_is_hashed_and_username_is_public_id(self) -> None:
        access = self.repository.authenticate_or_claim(self.profile, "Flamer_1", "correct horse")
        self.assertEqual((access.username, access.account_created), ("flamer_1", True))
        self.repository.authorize_session(self.profile.run_id, access.session_token)
        with closing(sqlite3.connect(self.repository.database_path)) as db:
            username, salt, digest = db.execute(
                "SELECT username,password_salt,password_hash FROM runs WHERE run_id=?", (self.profile.run_id,),
            ).fetchone()
        self.assertEqual(username, "flamer_1")
        self.assertNotIn(b"correct horse", bytes(salt) + bytes(digest))
        with self.assertRaises(PermissionError):
            self.repository.authenticate_or_claim(self.profile, "flamer_1", "wrong password")

    def test_username_is_unique_across_runs(self) -> None:
        self.repository.authenticate_or_claim(self.profile, "flamer", "password one")
        other = RunProfile("blue-other-00001", "OTHER", GameVersion.BLUE)
        with self.assertRaisesRegex(ValueError, "already taken"):
            self.repository.authenticate_or_claim(other, "flamer", "password two")

    def test_legacy_json_snapshots_are_imported_once(self) -> None:
        root = Path(self.temporary.name) / "legacy"
        legacy = FileSnapshotRepository(root)
        legacy.upload_save(self.profile, self.save_bytes)
        sqlite_repository = SQLiteSnapshotRepository(root)
        self.assertEqual(len(sqlite_repository.list_snapshots(self.profile.run_id)), 1)
        SQLiteSnapshotRepository(root)
        self.assertEqual(len(sqlite_repository.list_snapshots(self.profile.run_id)), 1)


class SQLiteServerAuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.repository = SQLiteSnapshotRepository(cls.temporary.name)
        cls.server = NuzlockeHTTPServer(("127.0.0.1", 0), NuzlockeRequestHandler, repository=cls.repository)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.save_bytes = FIXTURE.read_bytes()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temporary.cleanup()

    def test_username_password_session_and_read_only_friend_view(self) -> None:
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        request = Request(
            f"{self.base_url}/api/inspect?version=blue", data=self.save_bytes, method="POST",
            headers={"Content-Type": "application/octet-stream", "X-Run-Username": "flamer", "X-Run-Password": "strong password"},
        )
        with opener.open(request, timeout=3) as response:
            payload = json.load(response)
            self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertEqual(payload["sharing"]["username"], "flamer")
        self.assertTrue(payload["sharing"]["account_created"])
        with urlopen(f"{self.base_url}/api/view?username=flamer", timeout=3) as response:
            shared = json.load(response)
        self.assertEqual(shared["sharing"]["role"], "viewer")
        self.assertNotIn("run_id", shared)
        self.assertNotIn("save_sha256", json.dumps(shared))
        encounter = Request(
            f"{self.base_url}/api/encounters", method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps({
                "run_id": payload["run_id"], "area_id": "route_2", "status": "caught",
                "species_id": 0x24, "nickname": "Birb", "method": "grass", "level": 3,
            }).encode(),
        )
        with opener.open(encounter, timeout=3) as response:
            self.assertEqual(response.status, 201)
        unauthorized = Request(
            f"{self.base_url}/api/encounters", method="POST",
            headers={"Content-Type": "application/json"}, data=encounter.data,
        )
        with self.assertRaises(HTTPError) as denied:
            urlopen(unauthorized, timeout=3)
        self.assertEqual(denied.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
