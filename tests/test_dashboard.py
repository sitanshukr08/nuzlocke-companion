import json
from copy import deepcopy
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from gen1_save_parser import GameVersion, parse_save_bytes
from nuzlocke_app.dashboard import build_dashboard_payload
from nuzlocke_app.progress import FileSnapshotRepository, RunProfile
from nuzlocke_app.rules import EncounterRecord, EncounterStatus, RunHistory
from nuzlocke_app.server import NuzlockeHTTPServer, NuzlockeRequestHandler


FIXTURES = Path(__file__).parent / "fixtures"


class DashboardPayloadTests(unittest.TestCase):
    def test_dashboard_preserves_declared_red_version(self) -> None:
        state = parse_save_bytes(
            (FIXTURES / "pokemon_blue.sav").read_bytes(),
            expected_version=GameVersion.RED,
        )
        self.assertTrue(state.is_valid)
        self.assertEqual(build_dashboard_payload(state)["trainer"]["version"], "red")

    def test_cerulean_map_uses_exact_save_tile_coordinates(self) -> None:
        state = parse_save_bytes(
            (FIXTURES / "pokemon_blue.sav").read_bytes(),
            expected_version=GameVersion.BLUE,
        )
        state = deepcopy(state)
        state.current_map_id = 0x03
        state.location_id = "cerulean_city"
        state.location_name = "Cerulean City"
        state.player_x = 19
        state.player_y = 18

        view = build_dashboard_payload(state)["location"]["map_view"]

        self.assertEqual(view["precision"], "exact_tile")
        self.assertEqual((view["width_tiles"], view["height_tiles"]), (40, 36))
        self.assertEqual(view["asset"], "assets/maps/cerulean-city-rby.png")
        self.assertAlmostEqual(view["marker_left_percent"], 48.75)
        self.assertAlmostEqual(view["marker_top_percent"], 51.388888888888886)

    def test_early_save_projects_verified_dashboard_facts(self) -> None:
        state = parse_save_bytes(
            (FIXTURES / "pokemon_blue.sav").read_bytes(),
            expected_version=GameVersion.BLUE,
        )
        payload = build_dashboard_payload(state)

        self.assertEqual((payload["trainer"]["name"], payload["location"]["name"]), ("FLAMER", "Pewter City"))
        self.assertEqual([mon["nickname"] for mon in payload["party"]], ["Potion", "Keeda", "RealFlamer"])
        self.assertEqual((payload["objective"]["boss"], payload["objective"]["level_cap"]), ("Brock", 14))
        self.assertEqual(payload["objective"]["trainers"][0]["party"][0]["dex_number"], 50)
        self.assertEqual(payload["next_trainer"]["trainer_class"], "Jr. Trainer♂")
        self.assertEqual(payload["reachable_trainers"][0]["trainer_id"], payload["next_trainer"]["trainer_id"])
        route_2_catalog = next(area for area in payload["encounter_catalog"] if area["area_id"] == "route_2")
        self.assertIn("Pidgey", {choice["species_name"] for choice in route_2_catalog["choices"]})
        self.assertEqual(payload["encounter_history"], [])
        self.assertEqual(payload["defeated_trainer_count"], 4)
        route_3 = next(area for area in payload["areas"] if area["area_id"] == "route_3")
        self.assertEqual((route_3["encounter_status"], route_3["progression_accessible"]), ("unknown", False))
        route_2 = next(area for area in payload["areas"] if area["area_id"] == "route_2")
        self.assertEqual({item["access_status"] for item in route_2["items"]}, {"locked"})
        self.assertTrue(all("Cut" in item["access_requirement"] for item in route_2["items"]))
        self.assertFalse(payload["field_capabilities"]["cut"])
        self.assertEqual(
            [(item["display_name"], item["quantity"]) for item in payload["inventory"]["bag"]],
            [("Town Map", 1), ("Poké Ball", 4), ("Potion", 6), ("Antidote", 1)],
        )
        self.assertEqual(payload["inventory"]["pc"], [])
        self.assertEqual(
            len({area["map_id"] for area in payload["areas"]}),
            len(payload["areas"]),
        )
        self.assertEqual(payload["boxes"]["box_count"], 12)
        self.assertEqual(payload["boxes"]["entries"][0]["status"], "current_cache")
        self.assertTrue(all(
            box["status"] == "uninitialized" for box in payload["boxes"]["entries"][1:]
        ))
        self.assertNotIn("EVENT_GOT_TM42", payload["completed_story_events"])

    def test_current_map_is_not_repeated_as_a_nearby_item_area(self) -> None:
        state = parse_save_bytes(
            (FIXTURES / "pokemon_blue.sav").read_bytes(),
            expected_version=GameVersion.BLUE,
        )
        state = deepcopy(state)
        state.current_map_id = 0x0F
        state.location_id = "route_4"
        state.location_name = "Route 4"
        state.player_x, state.player_y = 5, 5
        payload = build_dashboard_payload(state)
        area_map_ids = [area["map_id"] for area in payload["areas"]]
        self.assertEqual(len(area_map_ids), len(set(area_map_ids)))
        self.assertTrue(payload["items_here"])
        json.dumps(payload)

    def test_manual_encounter_history_is_projected_for_the_active_ui(self) -> None:
        state = parse_save_bytes(
            (FIXTURES / "pokemon_blue.sav").read_bytes(),
            expected_version=GameVersion.BLUE,
        )
        history = RunHistory(encounters=(EncounterRecord(
            "route_2", EncounterStatus.CAUGHT, species_id=0x24,
            nickname="Birb", method="grass", level=3,
        ),))
        payload = build_dashboard_payload(state, history)
        self.assertEqual(payload["encounter_history"], [{
            "area_id": "route_2", "map_name": "Route 2", "status": "caught",
            "species_id": 0x24, "species_name": "Pidgey", "dex_number": 16,
            "nickname": "Birb", "method": "grass", "level": 3,
            "source": "wild", "notes": None,
        }])

    def test_evolved_party_member_links_to_caught_level_by_nickname(self) -> None:
        state = parse_save_bytes(
            (FIXTURES / "pokemon_blue.sav").read_bytes(),
            expected_version=GameVersion.BLUE,
        )
        history = RunHistory(encounters=(EncounterRecord(
            "route_2", EncounterStatus.CAUGHT, species_id=123,
            nickname="Keeda", method="grass", level=3,
        ),))
        payload = build_dashboard_payload(state, history)
        butterfree = next(mon for mon in payload["party"] if mon["nickname"] == "Keeda")
        self.assertEqual(butterfree["species_name"], "Butterfree")
        self.assertEqual(butterfree["met_data_source"], "not_stored_in_generation_i_save")
        self.assertEqual(butterfree["encounter_origin"], {
            "area_id": "route_2", "map_name": "Route 2", "caught_level": 3,
            "method": "grass", "source": "wild", "recorded_species_name": "Caterpie",
            "match_basis": "nickname", "evidence": "user_confirmed_manual_history",
        })

    def test_completed_save_has_no_remaining_objective(self) -> None:
        state = parse_save_bytes(
            (FIXTURES / "pokemon_blue_completed_online.sav").read_bytes(),
            expected_version=GameVersion.BLUE,
        )
        payload = build_dashboard_payload(state)
        self.assertEqual(len(payload["badges"]), 8)
        self.assertEqual(payload["progress"], {"completed": 13, "total": 13})
        self.assertIsNone(payload["objective"])
        self.assertIsNone(payload["next_trainer"])
        self.assertEqual(payload["defeated_trainer_count"], 329)
        self.assertEqual(payload["boxes"]["observed_pokemon"], 20)
        bulbasaur = payload["boxes"]["entries"][0]["members"][0]
        self.assertEqual((bulbasaur["nickname"], bulbasaur["level"]), ("BULBASAUR", 5))
        self.assertEqual(bulbasaur["calculated_stats"], {
            "hp": 20, "attack": 11, "defense": 11, "speed": 9, "special": 11,
        })
        self.assertEqual(
            bulbasaur["stats_evidence"],
            "calculated_from_stored_level_dvs_stat_experience_and_canonical_base_stats",
        )


class DashboardServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.repository = FileSnapshotRepository(cls.temporary.name)
        cls.server = NuzlockeHTTPServer(
            ("127.0.0.1", 0), NuzlockeRequestHandler,
            repository=cls.repository,
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        state = parse_save_bytes(
            (FIXTURES / "pokemon_blue.sav").read_bytes(), expected_version=GameVersion.BLUE,
        )
        cls.run_id = NuzlockeRequestHandler._run_id(state)
        access = cls.repository.authorize_or_claim_owner(
            RunProfile(cls.run_id, state.player_name, GameVersion.BLUE), None,
        )
        cls.owner_key = access.issued_owner_key
        cls.viewer_code = access.viewer_code

    @classmethod
    def inspect_headers(cls) -> dict[str, str]:
        return {
            "Content-Type": "application/octet-stream",
            "X-Run-Owner-Keys": json.dumps({cls.run_id: cls.owner_key}),
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temporary.cleanup()

    def test_static_ui_and_save_api(self) -> None:
        with urlopen(f"{self.base_url}/", timeout=3) as response:
            html = response.read()
            self.assertIn(b"LOAD A GENERATION I SAVE", html)
            self.assertIn(b"PC BOXES", html)
            self.assertIn(b"RUN HISTORY", html)
        with urlopen(f"{self.base_url}/assets/trainers/brock.png", timeout=3) as response:
            self.assertEqual((response.status, response.headers.get_content_type()), (200, "image/png"))
        with urlopen(f"{self.base_url}/assets/badges.png", timeout=3) as response:
            self.assertEqual((response.status, response.headers.get_content_type()), (200, "image/png"))
        with urlopen(f"{self.base_url}/assets/item-ball.png", timeout=3) as response:
            self.assertEqual((response.status, response.headers.get_content_type()), (200, "image/png"))
        app_js = (Path(__file__).parents[1] / "nuzlocke_app" / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn('data.trainer?.version || data.game_version', app_js)
        self.assertIn('navigator.clipboard?.writeText', app_js)
        self.assertIn('document.execCommand("copy")', app_js)
        request = Request(
            f"{self.base_url}/api/inspect?version=blue",
            data=(FIXTURES / "pokemon_blue.sav").read_bytes(),
            headers=self.inspect_headers(),
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            payload = json.load(response)
        self.assertEqual(payload["trainer"]["name"], "FLAMER")
        self.assertRegex(payload["run_id"], r"^blue-flamer-\d{5}$")
        self.assertGreaterEqual(payload["run_history"]["total_snapshots"], 1)
        self.assertTrue(payload["run_history"]["entries"][0]["is_latest"])
        self.assertEqual(payload["run_history"]["time_basis"], "local_server_upload_time_utc")
        self.assertEqual(payload["sharing"]["viewer_code"], self.viewer_code)
        self.assertNotIn("owner_key_sha256", json.dumps(payload))
        with urlopen(f"{self.base_url}/api/view?code={self.viewer_code}", timeout=3) as response:
            shared = json.load(response)
        self.assertEqual(shared["sharing"], {"role": "viewer", "viewer_code": self.viewer_code})
        self.assertNotIn("run_id", shared)
        self.assertNotIn("save_sha256", json.dumps(shared))

    def test_encounter_api_persists_validated_history_across_save_reloads(self) -> None:
        save_bytes = (FIXTURES / "pokemon_blue.sav").read_bytes()
        inspect = Request(
            f"{self.base_url}/api/inspect?version=blue", data=save_bytes,
            headers=self.inspect_headers(), method="POST",
        )
        with urlopen(inspect, timeout=3) as response:
            initial = json.load(response)
        encounter = Request(
            f"{self.base_url}/api/encounters",
            data=json.dumps({
                "run_id": initial["run_id"], "area_id": "route_2", "status": "caught",
                "species_id": 0x24, "nickname": "Birb", "method": "grass",
                "level": 3, "source": "wild",
            }).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Run-Owner-Key": self.owner_key}, method="POST",
        )
        with urlopen(encounter, timeout=3) as response:
            self.assertEqual((response.status, json.load(response)["status"]), (201, "recorded"))
        with urlopen(inspect, timeout=3) as response:
            reloaded = json.load(response)
        self.assertEqual(reloaded["encounter_history"][0]["nickname"], "Birb")
        route_2 = next(area for area in reloaded["areas"] if area["area_id"] == "route_2")
        self.assertEqual(route_2["encounter_status"], "consumed")

    def test_invalid_save_returns_structured_422(self) -> None:
        request = Request(
            f"{self.base_url}/api/inspect?version=blue",
            data=bytes(32768),
            method="POST",
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=3)
        self.assertEqual(raised.exception.code, 422)
        payload = json.load(raised.exception)
        self.assertEqual(payload["error"], "save_validation_failed")
        self.assertTrue(payload["diagnostics"])

    def test_server_port_cannot_be_shared_by_a_second_instance(self) -> None:
        first = NuzlockeHTTPServer(("127.0.0.1", 0), NuzlockeRequestHandler)
        try:
            with self.assertRaises(OSError):
                NuzlockeHTTPServer(
                    ("127.0.0.1", first.server_port),
                    NuzlockeRequestHandler,
                )
        finally:
            first.server_close()


if __name__ == "__main__":
    unittest.main()
