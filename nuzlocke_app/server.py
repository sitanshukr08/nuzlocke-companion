"""Standard-library local server for the Nuzlocke Companion UI."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from gen1_save_parser import GameVersion, parse_save_bytes

from .dashboard import build_dashboard_payload
from .progress import FileSnapshotRepository, RunProfile, build_run_history
from .rules import EncounterRecord, EncounterSource, EncounterStatus, RunHistory
from .sqlite_repository import SQLiteSnapshotRepository


STATIC_ROOT = Path(__file__).parent / "web"
DEFAULT_DATA_ROOT = Path(os.environ.get(
    "NUZLOCKE_DATA_ROOT",
    str(Path(__file__).resolve().parent.parent / ".nuzlocke_data"),
))
MAX_UPLOAD_BYTES = 1024 * 1024
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
}


class NuzlockeHTTPServer(ThreadingHTTPServer):
    """Local server that refuses to share its port with a stale instance."""

    allow_reuse_address = False
    allow_reuse_port = False

    def __init__(self, *args: object, repository: FileSnapshotRepository | SQLiteSnapshotRepository | None = None, **kwargs: object) -> None:
        self.repository = repository or SQLiteSnapshotRepository(DEFAULT_DATA_ROOT)
        super().__init__(*args, **kwargs)

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class NuzlockeRequestHandler(BaseHTTPRequestHandler):
    server_version = "NuzlockeCompanion/0.1"

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; img-src 'self' https://raw.githubusercontent.com data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )

    def _json(self, status: int, payload: dict[str, object], *, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _owner_key_for_run(self, run_id: str) -> str | None:
        direct = self.headers.get("X-Run-Owner-Key")
        if direct:
            return direct[:256]
        encoded = self.headers.get("X-Run-Owner-Keys", "")
        if not encoded or len(encoded) > 16_384:
            return None
        try:
            values = json.loads(encoded)
            value = values.get(run_id) if isinstance(values, dict) else None
            return str(value)[:256] if value else None
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def _session_token(self) -> str | None:
        try:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            value = cookie.get("nuzlocke_session")
            return value.value[:256] if value else None
        except Exception:
            return None

    def _session_cookie(self, token: str) -> str:
        secure = self.headers.get("X-Forwarded-Proto", "").casefold() == "https"
        return f"nuzlocke_session={token}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax{'; Secure' if secure else ''}"

    @staticmethod
    def _run_id(state: object) -> str:
        name = re.sub(r"[^a-z0-9]+", "-", str(getattr(state, "player_name", "player")).casefold()).strip("-") or "player"
        version = getattr(getattr(state, "game_version", None), "value", "unknown")
        return f"{version}-{name}-{int(getattr(state, 'player_id', 0)):05d}"[:64]

    def _repository(self) -> FileSnapshotRepository | SQLiteSnapshotRepository | None:
        value = getattr(self.server, "repository", None)
        return value if isinstance(value, (FileSnapshotRepository, SQLiteSnapshotRepository)) else None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/healthz":
            self._json(200, {"status": "ok"})
            return
        if path == "/api/view":
            repository = self._repository()
            try:
                query = parse_qs(parsed.query)
                public_id = query.get("username", query.get("code", [""]))[0]
                dashboard = repository.get_shared_dashboard(public_id) if repository is not None else None
                if dashboard is None:
                    self._json(404, {"error": "shared_run_not_found", "message": "No shared run matches that username."})
                else:
                    self._json(200, dashboard)
            except (ValueError, OSError) as exc:
                self._json(400, {"error": "invalid_username", "message": str(exc)})
            return
        name = "index.html" if path == "/" else path.removeprefix("/")
        file_path = (STATIC_ROOT / name).resolve()
        if (
            file_path.suffix not in CONTENT_TYPES
            or not file_path.is_relative_to(STATIC_ROOT.resolve())
            or not file_path.is_file()
        ):
            self.send_error(404)
            return
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES[file_path.suffix])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/encounters":
            self._post_encounter()
            return
        if parsed.path != "/api/inspect":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_UPLOAD_BYTES:
                raise ValueError("upload must contain one save file no larger than 1 MiB")
            version_text = parse_qs(parsed.query).get("version", [""])[0]
            version = GameVersion(version_text)
            save_bytes = self.rfile.read(length)
            state = parse_save_bytes(save_bytes, expected_version=version)
            if not state.is_valid:
                self._json(422, {
                    "error": "save_validation_failed",
                    "status": state.status.value,
                    "diagnostics": [
                        {"code": item.code, "severity": item.severity.value, "message": item.message, "offset": item.offset}
                        for item in state.diagnostics
                    ],
                })
                return
            run_id = self._run_id(state)
            repository = self._repository()
            history = RunHistory()
            access = None
            snapshot = None
            if repository is not None:
                profile = RunProfile(run_id, state.player_name, version)
                if isinstance(repository, SQLiteSnapshotRepository):
                    access = repository.authenticate_or_claim(
                        profile,
                        self.headers.get("X-Run-Username", "")[:64],
                        self.headers.get("X-Run-Password", "")[:256],
                    )
                else:
                    access = repository.authorize_or_claim_owner(profile, self._owner_key_for_run(run_id))
                snapshot = repository.upload_save(profile, save_bytes)
                history = repository.get_run_history(run_id)
            payload = build_dashboard_payload(state, history)
            payload["run_id"] = run_id
            payload["run_history"] = (
                build_run_history(repository.list_snapshots(run_id))
                if repository is not None else build_run_history([])
            )
            response_headers = None
            if isinstance(repository, SQLiteSnapshotRepository) and access is not None:
                payload["sharing"] = {
                    "role": "owner", "username": access.username,
                    "account_created": access.account_created,
                    "viewer_path": f"/?user={access.username}",
                }
                response_headers = {"Set-Cookie": self._session_cookie(access.session_token)}
            else:
                payload["sharing"] = {
                    "role": "owner",
                    "viewer_code": access.viewer_code if access is not None else None,
                    "owner_key": access.issued_owner_key if access is not None else None,
                    "owner_key_issued": bool(access and access.issued_owner_key),
                    "viewer_path": f"/?view={access.viewer_code}" if access is not None else None,
                }
            if repository is not None and snapshot is not None:
                repository.publish_shared_dashboard(run_id, snapshot.snapshot_id, payload)
            self._json(200, payload, headers=response_headers)
        except PermissionError as exc:
            self._json(403, {"error": "owner_authorization_required", "message": str(exc)})
        except (ValueError, OSError) as exc:
            self._json(400, {"error": "invalid_request", "message": str(exc)})

    def _post_encounter(self) -> None:
        try:
            repository = self._repository()
            if repository is None:
                raise ValueError("encounter persistence is unavailable")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 64 * 1024:
                raise ValueError("encounter request must be valid JSON no larger than 64 KiB")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            run_id = str(data["run_id"])
            if isinstance(repository, SQLiteSnapshotRepository):
                repository.authorize_session(run_id, self._session_token())
            else:
                repository.authorize_owner(run_id, self._owner_key_for_run(run_id))
            record = EncounterRecord(
                area_id=str(data["area_id"]),
                status=EncounterStatus(data["status"]),
                species_id=int(data["species_id"]) if data.get("species_id") is not None else None,
                nickname=str(data["nickname"]) if data.get("nickname") else None,
                method=str(data["method"]) if data.get("method") else None,
                level=int(data["level"]) if data.get("level") is not None else None,
                source=EncounterSource(data.get("source", "wild")),
                notes=str(data["notes"]) if data.get("notes") else None,
            )
            event_id = repository.append_encounter_event(run_id, record)
            self._json(201, {"event_id": event_id, "run_id": run_id, "status": "recorded"})
        except PermissionError as exc:
            self._json(403, {"error": "owner_authorization_required", "message": str(exc)})
        except (KeyError, TypeError, ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": "invalid_encounter", "message": str(exc)})

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Nuzlocke Companion web UI")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    args = parser.parse_args()
    try:
        server = NuzlockeHTTPServer((args.host, args.port), NuzlockeRequestHandler)
    except OSError as exc:
        raise SystemExit(
            f"Could not start Nuzlocke Companion on http://{args.host}:{args.port}: "
            "the port is already in use. Close the existing server with Ctrl+C, "
            "or open the already-running app."
        ) from exc
    print(f"Nuzlocke Companion running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
