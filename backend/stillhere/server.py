"""Local HTTP adapter for C01; bind to loopback and put the UI behind the same origin."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from .commands import COMMAND_HANDLERS
from .agent import AgentConfig, AgentRuntime
from .agent.config import load_local_environment
from .contracts import InvalidInput, VERSION, canonical_json, validate
from .service import CaseService, ServiceError

MAX_BODY_BYTES = 64 * 1024


class CaseHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, service, agent_runtime=None):
        self.service = service
        self.agent_runtime = agent_runtime or AgentRuntime(service)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Avoid logging case IDs, private bodies, session tokens, or query strings.
        pass

    def _send(self, status, value):
        body = canonical_json(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _token(self):
        authorization = self.headers.get("Authorization", "")
        return authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else None

    def _body(self):
        if self.headers.get("Transfer-Encoding"):
            raise ServiceError(400, "invalid_request", "Use a Content-Length JSON request.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ServiceError(400, "invalid_request", "Invalid Content-Length.") from None
        if not 0 < length <= MAX_BODY_BYTES:
            raise ServiceError(400, "invalid_request", "JSON body must be between 1 and 65536 bytes.")
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise ServiceError(415, "invalid_request", "Use Content-Type: application/json.")

        def object_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate JSON key")
                result[key] = value
            return result

        def invalid_constant(value):
            raise ValueError("Non-finite JSON value")

        try:
            value = json.loads(self.rfile.read(length), object_pairs_hook=object_pairs, parse_constant=invalid_constant)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise ServiceError(400, "invalid_request", "Body must be valid JSON with unique keys and finite values.") from None
        if not isinstance(value, dict):
            raise ServiceError(400, "invalid_request", "JSON body must be an object.")
        return value

    def _dispatch(self):
        path = urlsplit(self.path).path
        if self.command == "GET" and path == "/health":
            return self._send(200, {"contract_version": VERSION, "status": "ok", "implemented_commands": list(COMMAND_HANDLERS)})
        if self.command == "GET" and path.startswith("/v1/cases/") and path.count("/") == 3:
            return self._send(200, self.server.service.read_case(
                self._token(), unquote(path.rsplit("/", 1)[1]), self.headers.get("X-Contract-Version")
            ))
        if self.command != "POST" or path not in ("/v1/sessions", "/v1/cases", "/v1/commands"):
            raise ServiceError(404, "route_unavailable", "Route is unavailable.")
        body = self._body()
        if path == "/v1/sessions":
            try:
                validate("SessionRequest", body)
            except InvalidInput:
                raise ServiceError(400, "invalid_request", "Session requests accept contract_version: 0.1 only; roles are server-owned.") from None
            return self._send(201, self.server.service.create_session())
        if path == "/v1/cases":
            result = self.server.service.create_case(self._token(), body)
        else:
            result = self.server.agent_runtime.handle(self._token(), body)
        status = {"applied": 200, "already_applied": 200, "conflict": 409, "rejected": 400, "unavailable": 503, "needs_clarification": 200}[result["status"]]
        codes = {issue["code"] for issue in result["issues"]}
        if "unauthorized" in codes:
            status = 401
        elif "case_unavailable" in codes:
            status = 404
        elif "channel_forbidden" in codes:
            status = 403
        self._send(status, result)

    def do_GET(self):
        try:
            self._dispatch()
        except ServiceError as error:
            self._send(error.status, {"contract_version": VERSION, "error": error.issue})

    do_POST = do_GET


def main():
    parser = argparse.ArgumentParser(description="StillHere local case and agent service")
    parser.add_argument("--db", default="var/cases.sqlite3")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--env-file", help="Explicit optional local environment file, e.g. .env.local")
    args = parser.parse_args()
    if args.env_file:
        load_local_environment(args.env_file)
    service = CaseService(args.db)
    server = CaseHTTPServer(("127.0.0.1", args.port), service, AgentRuntime(service, AgentConfig.from_environment()))
    print(f"StillHere listening at http://127.0.0.1:{server.server_port}; contract {VERSION}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
