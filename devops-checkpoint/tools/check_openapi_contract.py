import json
import sys
from pathlib import Path


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_openapi_contract.py <openapi.json>")

    path = Path(sys.argv[1])
    contract = json.loads(path.read_text(encoding="utf-8"))

    require(contract.get("openapi", "").startswith("3."), "OpenAPI 3.x version is required")
    require(contract.get("info", {}).get("title"), "info.title is required")
    require(contract.get("info", {}).get("version"), "info.version is required")

    paths = contract.get("paths")
    require(isinstance(paths, dict) and paths, "paths must be a non-empty object")

    for required_path in ("/health", "/v1/whoami", "/v1/rooms"):
        require(required_path in paths, f"{required_path} must be present")
        require("get" in paths[required_path], f"{required_path} must define GET")
        responses = paths[required_path]["get"].get("responses", {})
        require("200" in responses, f"{required_path} GET must define a 200 response")

    print(f"contract-ok {path}")


if __name__ == "__main__":
    main()
