$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$Services = @(
  @{ Slug = "api-gateway-bff"; Display = "API Gateway / BFF"; Context = "Edge"; Kind = "http"; Full = $true },
  @{ Slug = "realtime-gateway"; Display = "Realtime Gateway - SSE"; Context = "Edge"; Kind = "http"; Full = $false },
  @{ Slug = "identity-api"; Display = "Identity API"; Context = "Identity & Session"; Kind = "http"; Full = $false },
  @{ Slug = "session-control-publisher"; Display = "Session Control Publisher"; Context = "Identity & Session"; Kind = "worker"; Full = $false },
  @{ Slug = "identity-audit-worker"; Display = "Identity Audit Worker"; Context = "Identity & Session"; Kind = "worker"; Full = $false },
  @{ Slug = "room-command-api"; Display = "Room Command API"; Context = "Room Gameplay"; Kind = "http"; Full = $false },
  @{ Slug = "room-engine"; Display = "Room Engine Pods"; Context = "Room Gameplay"; Kind = "worker"; Full = $false },
  @{ Slug = "rng-deck-service"; Display = "RNG / Deck Service"; Context = "Room Gameplay"; Kind = "http"; Full = $false },
  @{ Slug = "room-timer-scheduler"; Display = "Room Timer Scheduler"; Context = "Room Gameplay"; Kind = "worker"; Full = $false },
  @{ Slug = "room-outbox-relay"; Display = "Room Outbox Relay"; Context = "Room Gameplay"; Kind = "worker"; Full = $false },
  @{ Slug = "room-query-api"; Display = "Room Query API"; Context = "Room Gameplay"; Kind = "http"; Full = $false },
  @{ Slug = "room-creation-command-consumer"; Display = "Room Creation Command Consumer"; Context = "Room Gameplay"; Kind = "worker"; Full = $false },
  @{ Slug = "room-log-replay-api"; Display = "Room Log Replay API"; Context = "Room Gameplay"; Kind = "http"; Full = $false },
  @{ Slug = "tournament-api"; Display = "Tournament API"; Context = "Tournament Orchestration"; Kind = "http"; Full = $false },
  @{ Slug = "tournament-orchestrator"; Display = "Tournament Orchestrator"; Context = "Tournament Orchestration"; Kind = "worker"; Full = $false },
  @{ Slug = "round-kickoff-planner"; Display = "Round Kickoff Planner"; Context = "Tournament Orchestration"; Kind = "worker"; Full = $false },
  @{ Slug = "round-provisioning-workers"; Display = "Round Provisioning Workers"; Context = "Tournament Orchestration"; Kind = "worker"; Full = $false },
  @{ Slug = "room-result-consumer"; Display = "Room Result Consumer"; Context = "Tournament Orchestration"; Kind = "worker"; Full = $false },
  @{ Slug = "bracket-event-publisher"; Display = "Bracket Event Publisher"; Context = "Tournament Orchestration"; Kind = "worker"; Full = $false },
  @{ Slug = "ranking-api"; Display = "Ranking API"; Context = "Ranking"; Kind = "http"; Full = $false },
  @{ Slug = "rating-command-consumer"; Display = "Rating Command Consumer"; Context = "Ranking"; Kind = "worker"; Full = $false },
  @{ Slug = "leaderboard-projection-workers"; Display = "Leaderboard Projection Workers"; Context = "Ranking"; Kind = "worker"; Full = $false },
  @{ Slug = "rating-audit-publisher"; Display = "Rating Audit Publisher"; Context = "Ranking"; Kind = "worker"; Full = $false },
  @{ Slug = "spectator-projection-ingestors"; Display = "Spectator Projection Ingestors"; Context = "Spectator View"; Kind = "worker"; Full = $false },
  @{ Slug = "public-room-view-api"; Display = "Public Room View API"; Context = "Spectator View"; Kind = "http"; Full = $false },
  @{ Slug = "public-tournament-view-api"; Display = "Public Tournament View API"; Context = "Spectator View"; Kind = "http"; Full = $false },
  @{ Slug = "spectator-stream-publisher"; Display = "Spectator Stream Publisher"; Context = "Spectator View"; Kind = "worker"; Full = $false },
  @{ Slug = "projection-schema-guard"; Display = "Projection Schema Guard"; Context = "Spectator View"; Kind = "worker"; Full = $false },
  @{ Slug = "audit-ingestor"; Display = "Audit Ingestor"; Context = "Compliance & Audit"; Kind = "worker"; Full = $false },
  @{ Slug = "dispute-replay-api"; Display = "Dispute Replay API"; Context = "Compliance & Audit"; Kind = "http"; Full = $false },
  @{ Slug = "audit-export-worker"; Display = "Audit Export Worker"; Context = "Compliance & Audit"; Kind = "worker"; Full = $false }
)

function Write-GeneratedFile {
  param([string] $Path, [string] $Content)
  $Parent = Split-Path -Parent $Path
  if ($Parent) {
    New-Item -ItemType Directory -Force -Path $Parent | Out-Null
  }
  [System.IO.File]::WriteAllText($Path, $Content, $Utf8NoBom)
}

function Get-ServiceJson {
  param($Service)
  $Slug = $Service.Slug
  if ($Slug -eq "api-gateway-bff") {
    $Routes = [ordered]@{
      "/v1/rooms" = [ordered]@{ result = "ok"; service = $Slug; rooms = @() }
      "/v1/whoami" = [ordered]@{ result = "ok"; service = $Slug; playerId = "placeholder-player"; sessionVersion = 1 }
    }
  } else {
    $Routes = [ordered]@{
      "/v1/placeholder" = [ordered]@{
        result = "ok"
        service = $Slug
        message = "$($Service.Display) placeholder response"
      }
    }
  }
  $Payload = [ordered]@{
    context = $Service.Context
    displayName = $Service.Display
    greeting = "UnoArena $($Service.Display) placeholder"
    kind = $Service.Kind
    routes = $Routes
    service = $Slug
  }
  return (($Payload | ConvertTo-Json -Depth 10) + "`n")
}

function Get-Dockerfile {
  param([string] $Slug)
  return @"
FROM python:3.12-slim

ENV PORT=8080 \
    SERVICE_CONFIG=/app/service.json \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY devops-checkpoint/runtime/app.py /app/app.py
COPY services/$Slug/service.json /app/service.json

RUN useradd --create-home --uid 10001 appuser
USER 10001

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).read()"

CMD ["python", "/app/app.py"]
"@
}

function Get-TestFile {
  param([string] $Slug)
  return @"
import json
from pathlib import Path


CONFIG = Path(__file__).with_name("service.json")


def main():
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert payload["service"] == "$Slug"
    assert payload["displayName"]
    assert payload["context"]
    assert payload["kind"] in {"http", "worker"}
    assert isinstance(payload["routes"], dict)
    assert "/health" not in payload["routes"]
    for route, response in payload["routes"].items():
        assert route.startswith("/")
        assert response["service"] == "$Slug"
        assert response["result"] == "ok"


if __name__ == "__main__":
    main()
"@
}

function Get-ChartYaml {
  param($Service)
  return @"
apiVersion: v2
name: $($Service.Slug)
description: UnoArena placeholder chart for $($Service.Display).
type: application
version: 0.1.0
appVersion: "0.1.0"
dependencies:
  - name: unoarena-placeholder-lib
    version: 0.1.0
    repository: file://../unoarena-placeholder-lib
"@
}

function Get-ValuesYaml {
  param($Service, [string] $Environment)
  $Replicas = 1
  $Cpu = "50m"
  $Memory = "64Mi"
  if ($Environment -eq "production") {
    $Replicas = if ($Service.Kind -eq "http") { 2 } else { 1 }
    if ($Service.Slug -in @("api-gateway-bff", "realtime-gateway")) {
      $Replicas = 3
    }
    $Cpu = "100m"
    $Memory = "128Mi"
  }
  $Repository = "registry.example.invalid/unoarena/$($Service.Slug)"
  $Tag = "dev"
  if ($Environment -in @("staging", "production")) {
    $Repository = ""
    $Tag = ""
  }
  return @"
serviceName: $($Service.Slug)
context: "$($Service.Context)"
replicaCount: $Replicas
image:
  repository: "$Repository"
  tag: "$Tag"
  digest: ""
  pullPolicy: IfNotPresent
containerPort: 8080
service:
  type: ClusterIP
  port: 80
env:
  UNOARENA_ENVIRONMENT: "$Environment"
  PLACEHOLDER_KIND: "$($Service.Kind)"
resources:
  requests:
    cpu: "$Cpu"
    memory: "$Memory"
  limits:
    cpu: "250m"
    memory: "256Mi"
"@
}

function Get-ChartTemplate {
  return @'
{{ include "unoarena-placeholder-lib.deployment" . }}
---
{{ include "unoarena-placeholder-lib.service" . }}
'@
}

function Get-RulesBlock {
  param([string] $Slug, [string[]] $Extra, [bool] $Manual = $false)
  $Paths = @(
    "services/$Slug/**/*",
    "deploy/helm/$Slug/**/*",
    ".gitlab-ci.yml",
    ".gitlab/ci/services/$Slug.yml",
    ".gitlab/ci/templates/service-placeholder.yml",
    "devops-checkpoint/runtime/**/*"
  ) + $Extra
  $Lines = @("  rules:", "    - changes:")
  foreach ($Path in $Paths) {
    $Lines += "        - $Path"
  }
  if ($Manual) {
    $Lines += "      when: manual"
  }
  $Lines += "    - when: never"
  return ($Lines -join "`n")
}

function Get-Fragment {
  param($Service)
  $Slug = $Service.Slug
  $Extra = @()
  if ($Slug -eq "api-gateway-bff") {
    $Extra = @("contracts/api-gateway-bff/**/*", "devops-checkpoint/smoke/**/*")
  }
  $Rules = Get-RulesBlock $Slug $Extra
  $ProdRules = Get-RulesBlock $Slug $Extra $true
  $Parts = @()
  if ($Slug -eq "api-gateway-bff") {
    $Parts += @"
${Slug}:contract:
  extends: .contract_json_check
  variables:
    CONTRACT_FILE: contracts/api-gateway-bff/openapi.json
$Rules
"@
  }
  $Parts += @"
${Slug}:test:
  extends: .service_test
  variables:
    SERVICE_SLUG: $Slug
$Rules
"@
  $Needs = "    - job: ${Slug}:test"
  if ($Slug -eq "api-gateway-bff") {
    $Needs += "`n    - job: ${Slug}:contract"
  }
  $Parts += @"
${Slug}:build:
  extends: .service_build
  variables:
    SERVICE_SLUG: $Slug
  needs:
$Needs
$Rules
"@
  $Parts += @"
${Slug}:deliver:
  extends: .service_deliver
  variables:
    SERVICE_SLUG: $Slug
  needs:
    - job: ${Slug}:build
      artifacts: true
$Rules
"@
  if ($Service.Full) {
    $Parts += @"
${Slug}:deploy-staging:
  extends: .service_deploy_staging
  variables:
    SERVICE_SLUG: $Slug
  needs:
    - job: ${Slug}:deliver
      artifacts: true
$Rules
"@
    $Parts += @"
${Slug}:integration-staging:
  extends: .service_integration_staging
  variables:
    SERVICE_SLUG: $Slug
    UNOARENA_API_URL: `${STAGING_BASE_URL}
  needs:
    - job: ${Slug}:deploy-staging
$Rules
"@
    $Parts += @"
${Slug}:deliver-production:
  extends: .service_deliver_production
  variables:
    SERVICE_SLUG: $Slug
  needs:
    - job: ${Slug}:deliver
      artifacts: true
$ProdRules
"@
    $Parts += @"
${Slug}:deploy-production:
  extends: .service_deploy_production
  variables:
    SERVICE_SLUG: $Slug
  needs:
    - job: ${Slug}:deliver-production
      artifacts: true
$ProdRules
"@
  }
  return (($Parts -join "`n") + "`n")
}

foreach ($Service in $Services) {
  $Slug = $Service.Slug
  $ServiceDir = Join-Path $Root "services\$Slug"
  Write-GeneratedFile (Join-Path $ServiceDir "service.json") (Get-ServiceJson $Service)
  Write-GeneratedFile (Join-Path $ServiceDir "Dockerfile") (Get-Dockerfile $Slug)
  Write-GeneratedFile (Join-Path $ServiceDir "test_placeholder.py") (Get-TestFile $Slug)

  $ChartDir = Join-Path $Root "deploy\helm\$Slug"
  Write-GeneratedFile (Join-Path $ChartDir "Chart.yaml") (Get-ChartYaml $Service)
  Write-GeneratedFile (Join-Path $ChartDir "templates\all.yaml") (Get-ChartTemplate)
  Write-GeneratedFile (Join-Path $ChartDir "values.yaml") (Get-ValuesYaml $Service "local")
  Write-GeneratedFile (Join-Path $ChartDir "values-staging.yaml") (Get-ValuesYaml $Service "staging")
  Write-GeneratedFile (Join-Path $ChartDir "values-production.yaml") (Get-ValuesYaml $Service "production")

  Write-GeneratedFile (Join-Path $Root ".gitlab\ci\services\$Slug.yml") (Get-Fragment $Service)
}

Write-Host "Generated $($Services.Count) service placeholders."
