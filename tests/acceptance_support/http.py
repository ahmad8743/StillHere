"""Same adapter dispatch via memory or real loopback; evidence stays distinct."""

from http.client import HTTPConnection
from io import BytesIO
import json
from types import SimpleNamespace
from email.message import Message

from backend.stillhere.server import Handler


class MemoryHTTP:
    """Exercise Handler JSON/auth/route/status logic, without claiming socket proof."""
    def __init__(self, service, runtime):
        self.server = SimpleNamespace(service=service, agent_runtime=runtime)

    def request(self, method, path, body=None, token=None, *, raw=None, headers=None):
        handler = Handler.__new__(Handler)
        handler.server = self.server
        handler.command, handler.path = method, path
        payload = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
        if isinstance(payload, str):
            payload = payload.encode()
        handler.headers = Message()
        values = {"Content-Type": "application/json", "Content-Length": str(len(payload)), "X-Contract-Version": "0.1"}
        if token:
            values["Authorization"] = "Bearer " + token
        values.update(headers or {})
        for key, value in values.items():
            handler.headers[key] = value
        handler.rfile = BytesIO(payload)
        output = []
        handler._send = lambda status, value: output.append((status, value, {}))
        handler.do_GET()
        return output[0]


class LoopbackHTTP:
    def __init__(self, server):
        self.server = server

    def request(self, method, path, body=None, token=None, *, raw=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        values = {"Content-Type": "application/json", "X-Contract-Version": "0.1"}
        if token:
            values["Authorization"] = "Bearer " + token
        values.update(headers or {})
        payload = raw if raw is not None else (json.dumps(body) if body is not None else None)
        try:
            connection.request(method, path, payload, values)
            response = connection.getresponse()
            return response.status, json.loads(response.read()), dict(response.getheaders())
        finally:
            connection.close()
