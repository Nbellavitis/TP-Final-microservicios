import json
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


CONFIG_PATH = Path(os.environ.get("SERVICE_CONFIG", "/app/service.json"))


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def json_bytes(payload):
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def health_payload(config):
    return {
        "status": "ok",
        "service": config["service"],
        "context": config["context"],
        "kind": config["kind"],
    }


def route_payload(config, path):
    if path == "/health":
        return 200, health_payload(config)
    if path == "/":
        return 200, {
            "service": config["service"],
            "message": config["greeting"],
            "routes": sorted(config.get("routes", {}).keys()),
        }
    routes = config.get("routes", {})
    if path in routes:
        return 200, routes[path]
    return 404, {
        "status": "not_found",
        "service": config["service"],
        "path": path,
    }


class PlaceholderHandler(BaseHTTPRequestHandler):
    server_version = "UnoArenaPlaceholder/1.0"

    def do_GET(self):
        self._handle_request()

    def do_POST(self):
        self._handle_request()

    def log_message(self, fmt, *args):
        return

    def _handle_request(self):
        parsed = urlparse(self.path)
        status_code, payload = route_payload(self.server.config, parsed.path)
        correlation_id = self.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        payload.setdefault("correlationId", correlation_id)
        body = json_bytes(payload)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Correlation-Id", correlation_id)
        self.end_headers()
        self.wfile.write(body)
        print(
            json.dumps(
                {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "level": "INFO",
                    "service": self.server.config["service"],
                    "method": self.command,
                    "path": parsed.path,
                    "status": status_code,
                    "correlationId": correlation_id,
                },
                sort_keys=True,
            ),
            flush=True,
        )


def main():
    config = load_config()
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), PlaceholderHandler)
    server.config = config
    print(
        json.dumps(
            {
                "level": "INFO",
                "service": config["service"],
                "message": "placeholder started",
                "port": port,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("shutdown requested", file=sys.stderr)


if __name__ == "__main__":
    main()
