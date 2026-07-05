import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


def parse_payloads(stdout):
    text = stdout.strip()
    if not text:
        raise AssertionError("CLI produced no output")
    try:
        return [json.loads(text)]
    except json.JSONDecodeError:
        payloads = []
        for line in text.splitlines():
            try:
                payloads.append(json.loads(line))
            except json.JSONDecodeError:
                if os.environ.get("UNOARENA_SMOKE_ALLOW_TEXT") == "true":
                    return text
                raise AssertionError(
                    "CLI smoke expected JSON or JSON-lines output. "
                    "Set UNOARENA_SMOKE_ALLOW_TEXT=true only for a documented temporary CLI gap."
                )
        return payloads


def assert_placeholder_response(stdout):
    expected = [
        marker.strip()
        for marker in os.environ.get("UNOARENA_SMOKE_EXPECT", "placeholder-player,api-gateway-bff").split(",")
        if marker.strip()
    ]
    parsed = parse_payloads(stdout)
    if isinstance(parsed, str):
        if any(marker in parsed for marker in expected):
            return
        if os.environ.get("UNOARENA_SMOKE_ALLOW_EXIT_ONLY") == "true":
            return
        raise AssertionError(f"CLI text output does not contain expected smoke marker {expected}: {parsed[:200]}")

    for payload in parsed:
        if isinstance(payload, list):
            if os.environ.get("UNOARENA_SMOKE_ALLOW_EMPTY_LIST", "true") == "true":
                return
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("service") == "api-gateway-bff" and payload.get("result") == "ok":
            return
        if payload.get("playerId") == "placeholder-player":
            return
        if isinstance(payload.get("rooms"), list):
            return
        serialized = json.dumps(payload, sort_keys=True)
        if any(marker in serialized for marker in expected):
            return

    if os.environ.get("UNOARENA_SMOKE_ALLOW_EXIT_ONLY") == "true":
        return
    raise AssertionError(f"CLI payload does not match api-gateway-bff placeholder contract: {parsed}")


def run_once(cli_path, args, base_url):
    env = os.environ.copy()
    env["UNOARENA_API_URL"] = base_url
    command = [cli_path] + args
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        env=env,
        text=True,
        timeout=20,
    )
    if completed.returncode != 0:
        raise AssertionError(
            "CLI command failed with exit code "
            f"{completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}"
        )
    assert_placeholder_response(completed.stdout)


def is_truthy(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def print_dry_run(cli_path, args, base_url):
    print(
        json.dumps(
            {
                "status": "ok",
                "smoke": "api-gateway-bff",
                "mode": "dry-run",
                "cli": cli_path,
                "args": args,
                "target": base_url,
            },
            sort_keys=True,
        )
    )


def main():
    base_url = os.environ.get("UNOARENA_API_URL") or os.environ.get("STAGING_BASE_URL")
    cli_path = os.environ.get("UNOARENA_CLI", "client-checkpoint/unoarena")
    args = shlex.split(os.environ.get("UNOARENA_CLI_SMOKE_ARGS", "whoami --json"))

    if is_truthy(os.environ.get("UNOARENA_SMOKE_DRY_RUN", "false")):
        print_dry_run(cli_path, args, base_url or "https://api-gateway-bff.unoarena-staging.placeholder")
        return

    if not base_url:
        raise SystemExit("UNOARENA_API_URL or STAGING_BASE_URL must point to the staging api-gateway-bff URL")

    if not Path(cli_path).exists():
        raise SystemExit(f"Client CLI not found at {cli_path}; set UNOARENA_CLI to the Client Checkpoint binary")

    failures = []
    for attempt in range(2):
        try:
            run_once(cli_path, args, base_url)
            print(json.dumps({"status": "ok", "smoke": "api-gateway-bff", "attempt": attempt + 1}))
            return
        except Exception as exc:
            failures.append(str(exc))
            if attempt == 0:
                time.sleep(2)
    raise SystemExit("CLI smoke failed after one retry: " + " | ".join(failures))


if __name__ == "__main__":
    main()
