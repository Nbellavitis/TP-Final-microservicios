import json
from pathlib import Path


CONFIG = Path(__file__).with_name("service.json")


def main():
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert payload["service"] == "tournament-api"
    assert payload["displayName"]
    assert payload["context"]
    assert payload["kind"] in {"http", "worker"}
    assert isinstance(payload["routes"], dict)
    assert "/health" not in payload["routes"]
    for route, response in payload["routes"].items():
        assert route.startswith("/")
        assert response["service"] == "tournament-api"
        assert response["result"] == "ok"


if __name__ == "__main__":
    main()