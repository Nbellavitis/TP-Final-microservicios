import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


SERVICES = [
    {
        "slug": "api-gateway-bff",
        "display": "API Gateway / BFF",
        "context": "Edge",
        "kind": "http",
        "full": True,
        "routes": {
            "/v1/rooms": {"result": "ok", "service": "api-gateway-bff", "rooms": []},
            "/v1/whoami": {
                "result": "ok",
                "service": "api-gateway-bff",
                "playerId": "placeholder-player",
                "sessionVersion": 1,
            },
        },
    },
    {"slug": "realtime-gateway", "display": "Realtime Gateway - SSE", "context": "Edge", "kind": "http"},
    {"slug": "identity-api", "display": "Identity API", "context": "Identity & Session", "kind": "http"},
    {"slug": "session-control-publisher", "display": "Session Control Publisher", "context": "Identity & Session", "kind": "worker"},
    {"slug": "identity-audit-worker", "display": "Identity Audit Worker", "context": "Identity & Session", "kind": "worker"},
    {"slug": "room-command-api", "display": "Room Command API", "context": "Room Gameplay", "kind": "http"},
    {"slug": "room-engine", "display": "Room Engine Pods", "context": "Room Gameplay", "kind": "worker"},
    {"slug": "rng-deck-service", "display": "RNG / Deck Service", "context": "Room Gameplay", "kind": "http"},
    {"slug": "room-timer-scheduler", "display": "Room Timer Scheduler", "context": "Room Gameplay", "kind": "worker"},
    {"slug": "room-outbox-relay", "display": "Room Outbox Relay", "context": "Room Gameplay", "kind": "worker"},
    {"slug": "room-query-api", "display": "Room Query API", "context": "Room Gameplay", "kind": "http"},
    {"slug": "room-creation-command-consumer", "display": "Room Creation Command Consumer", "context": "Room Gameplay", "kind": "worker"},
    {"slug": "room-log-replay-api", "display": "Room Log Replay API", "context": "Room Gameplay", "kind": "http"},
    {"slug": "tournament-api", "display": "Tournament API", "context": "Tournament Orchestration", "kind": "http"},
    {"slug": "tournament-orchestrator", "display": "Tournament Orchestrator", "context": "Tournament Orchestration", "kind": "worker"},
    {"slug": "round-kickoff-planner", "display": "Round Kickoff Planner", "context": "Tournament Orchestration", "kind": "worker"},
    {"slug": "round-provisioning-workers", "display": "Round Provisioning Workers", "context": "Tournament Orchestration", "kind": "worker"},
    {"slug": "room-result-consumer", "display": "Room Result Consumer", "context": "Tournament Orchestration", "kind": "worker"},
    {"slug": "bracket-event-publisher", "display": "Bracket Event Publisher", "context": "Tournament Orchestration", "kind": "worker"},
    {"slug": "ranking-api", "display": "Ranking API", "context": "Ranking", "kind": "http"},
    {"slug": "rating-command-consumer", "display": "Rating Command Consumer", "context": "Ranking", "kind": "worker"},
    {"slug": "leaderboard-projection-workers", "display": "Leaderboard Projection Workers", "context": "Ranking", "kind": "worker"},
    {"slug": "rating-audit-publisher", "display": "Rating Audit Publisher", "context": "Ranking", "kind": "worker"},
    {"slug": "spectator-projection-ingestors", "display": "Spectator Projection Ingestors", "context": "Spectator View", "kind": "worker"},
    {"slug": "public-room-view-api", "display": "Public Room View API", "context": "Spectator View", "kind": "http"},
    {"slug": "public-tournament-view-api", "display": "Public Tournament View API", "context": "Spectator View", "kind": "http"},
    {"slug": "spectator-stream-publisher", "display": "Spectator Stream Publisher", "context": "Spectator View", "kind": "worker"},
    {"slug": "projection-schema-guard", "display": "Projection Schema Guard", "context": "Spectator View", "kind": "worker"},
    {"slug": "audit-ingestor", "display": "Audit Ingestor", "context": "Compliance & Audit", "kind": "worker"},
    {"slug": "dispute-replay-api", "display": "Dispute Replay API", "context": "Compliance & Audit", "kind": "http"},
    {"slug": "audit-export-worker", "display": "Audit Export Worker", "context": "Compliance & Audit", "kind": "worker"},
]


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def default_routes(service):
    if service.get("routes"):
        return service["routes"]
    slug = service["slug"]
    if service["kind"] == "http":
        return {
            "/v1/placeholder": {
                "result": "ok",
                "service": slug,
                "message": f"{service['display']} placeholder response",
            }
        }
    return {
        "/v1/placeholder": {
            "result": "ok",
            "service": slug,
            "message": f"{service['display']} worker placeholder heartbeat",
        }
    }


def service_json(service):
    payload = {
        "service": service["slug"],
        "displayName": service["display"],
        "context": service["context"],
        "kind": service["kind"],
        "greeting": f"UnoArena {service['display']} placeholder",
        "routes": default_routes(service),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def dockerfile(slug):
    return f"""FROM python:3.12-slim

ENV PORT=8080 \\
    SERVICE_CONFIG=/app/service.json \\
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY devops-checkpoint/runtime/app.py /app/app.py
COPY services/{slug}/service.json /app/service.json

RUN useradd --create-home --uid 10001 appuser
USER 10001

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).read()"

CMD ["python", "/app/app.py"]
"""


def test_file(slug):
    return f"""import json
from pathlib import Path


CONFIG = Path(__file__).with_name("service.json")


def main():
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert payload["service"] == "{slug}"
    assert payload["displayName"]
    assert payload["context"]
    assert payload["kind"] in {{"http", "worker"}}
    assert isinstance(payload["routes"], dict)
    assert "/health" not in payload["routes"]
    for route, response in payload["routes"].items():
        assert route.startswith("/")
        assert response["service"] == "{slug}"
        assert response["result"] == "ok"


if __name__ == "__main__":
    main()
"""


def chart_yaml(service):
    slug = service["slug"]
    return f"""apiVersion: v2
name: {slug}
description: UnoArena placeholder chart for {service['display']}.
type: application
version: 0.1.0
appVersion: "0.1.0"
dependencies:
  - name: unoarena-placeholder-lib
    version: 0.1.0
    repository: file://../unoarena-placeholder-lib
"""


def chart_values(service, environment):
    replicas = 1
    cpu = "50m"
    memory = "64Mi"
    if environment == "production":
        replicas = 2 if service["kind"] == "http" else 1
        if service["slug"] in {"api-gateway-bff", "realtime-gateway"}:
            replicas = 3
        cpu = "100m"
        memory = "128Mi"
    repo = "registry.example.invalid/unoarena/" + service["slug"]
    tag = "dev"
    service_type = "ClusterIP"
    if environment in {"staging", "production"}:
        repo = ""
        tag = ""
    payload = {
        "serviceName": service["slug"],
        "context": service["context"],
        "replicaCount": replicas,
        "image": {"repository": repo, "tag": tag, "digest": "", "pullPolicy": "IfNotPresent"},
        "containerPort": 8080,
        "service": {"type": service_type, "port": 80},
        "env": {
            "UNOARENA_ENVIRONMENT": environment,
            "PLACEHOLDER_KIND": service["kind"],
        },
        "resources": {
            "requests": {"cpu": cpu, "memory": memory},
            "limits": {"cpu": "250m", "memory": "256Mi"},
        },
    }
    return json.dumps(payload, indent=2, sort_keys=False).replace("{", "{").replace("}", "}") + "\n"


def chart_template():
    return """{{ include "unoarena-placeholder-lib.deployment" . }}
---
{{ include "unoarena-placeholder-lib.service" . }}
"""


def rules_block(slug, extra=None, indent="  ", manual=False):
    paths = [
        f"services/{slug}/**/*",
        f"deploy/helm/{slug}/**/*",
        ".gitlab-ci.yml",
        f".gitlab/ci/services/{slug}.yml",
        ".gitlab/ci/templates/service-placeholder.yml",
        "devops-checkpoint/runtime/**/*",
    ]
    if extra:
        paths.extend(extra)
    lines = [f"{indent}rules:"]
    if manual:
        lines.append(f"{indent}  - if: '$CI_COMMIT_TAG || $CI_COMMIT_REF_PROTECTED == \"true\"'")
        lines.append(f"{indent}    changes:")
    else:
        lines.append(f"{indent}  - changes:")
    lines.extend(f"{indent}      - {path}" for path in paths)
    if manual:
        lines.append(f"{indent}    when: manual")
    lines.append(f"{indent}  - when: never")
    return "\n".join(lines)


def fragment(service):
    slug = service["slug"]
    extra = []
    if slug == "api-gateway-bff":
        extra = [
            "contracts/api-gateway-bff/**/*",
            "devops-checkpoint/smoke/**/*",
        ]
    parts = []
    if slug == "api-gateway-bff":
        parts.append(f"""{slug}:contract:
  extends: .contract_json_check
  variables:
    CONTRACT_FILE: contracts/api-gateway-bff/openapi.json
{rules_block(slug, extra)}
""")
    parts.append(f"""{slug}:test:
  extends: .service_test
  variables:
    SERVICE_SLUG: {slug}
{rules_block(slug, extra)}
""")
    needs = [f"{slug}:test"]
    if slug == "api-gateway-bff":
        needs.append(f"{slug}:contract")
    needs_yaml = "\n".join(f"    - job: {job}" for job in needs)
    parts.append(f"""{slug}:build:
  extends: .service_build
  variables:
    SERVICE_SLUG: {slug}
  needs:
{needs_yaml}
{rules_block(slug, extra)}
""")
    parts.append(f"""{slug}:deliver:
  extends: .service_deliver
  variables:
    SERVICE_SLUG: {slug}
  needs:
    - job: {slug}:build
      artifacts: true
{rules_block(slug, extra)}
""")
    if service.get("full"):
        parts.append(f"""{slug}:deploy-staging:
  extends: .service_deploy_staging
  variables:
    SERVICE_SLUG: {slug}
  needs:
    - job: {slug}:deliver
      artifacts: true
{rules_block(slug, extra)}
""")
        parts.append(f"""{slug}:integration-staging:
  extends: .service_integration_staging
  variables:
    SERVICE_SLUG: {slug}
  needs:
    - job: {slug}:deploy-staging
      artifacts: true
{rules_block(slug, extra)}
""")
        parts.append(f"""{slug}:deliver-production:
  extends: .service_deliver_production
  variables:
    SERVICE_SLUG: {slug}
  needs:
    - job: {slug}:deliver
      artifacts: true
{rules_block(slug, extra, manual=True)}
""")
        parts.append(f"""{slug}:deploy-production:
  extends: .service_deploy_production
  variables:
    SERVICE_SLUG: {slug}
  needs:
    - job: {slug}:deliver-production
      artifacts: true
{rules_block(slug, extra, manual=True)}
""")
    return "\n".join(parts)


def main():
    for service in SERVICES:
        slug = service["slug"]
        service_dir = ROOT / "services" / slug
        write(service_dir / "service.json", service_json(service))
        write(service_dir / "Dockerfile", dockerfile(slug))
        write(service_dir / "test_placeholder.py", test_file(slug))

        chart_dir = ROOT / "deploy" / "helm" / slug
        write(chart_dir / "Chart.yaml", chart_yaml(service))
        write(chart_dir / "templates" / "all.yaml", chart_template())
        write(chart_dir / "values.yaml", chart_values(service, "local"))
        write(chart_dir / "values-staging.yaml", chart_values(service, "staging"))
        write(chart_dir / "values-production.yaml", chart_values(service, "production"))

        write(ROOT / ".gitlab" / "ci" / "services" / f"{slug}.yml", fragment(service))


if __name__ == "__main__":
    main()
