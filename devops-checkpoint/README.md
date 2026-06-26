# DevOps Checkpoint - UnoArena

This checkpoint proves that the architecture decomposition can be built, delivered, and deployed independently. The services are intentionally placeholders: they expose `/health`, return canned JSON, and do not implement real Uno gameplay.

Green pipeline run: **pending after first push to GitLab**. Paste the GitLab pipeline URL here once `api-gateway-bff:integration-staging` has passed on the submission branch.

## Layout

| Path | Purpose |
|---|---|
| `.gitlab-ci.yml` | Root GitLab pipeline with the required stage spine. |
| `.gitlab/ci/templates/service-placeholder.yml` | Reusable test/build/deliver/deploy/smoke job templates. |
| `.gitlab/ci/services/<service>.yml` | One pipeline fragment per service with path-based `rules:changes`. |
| `services/<service>/` | Placeholder source contract: `service.json`, `Dockerfile`, and `test_placeholder.py`. |
| `deploy/helm/<service>/` | One Helm chart per service. |
| `deploy/helm/unoarena-placeholder-lib/` | Shared Helm library chart used only to avoid duplicating Kubernetes YAML. |
| `contracts/api-gateway-bff/openapi.json` | Illustrative sync contract check for the fully wired service. |
| `devops-checkpoint/smoke/api_gateway_bff_cli_smoke.py` | Staging smoke test that invokes the Client Checkpoint CLI. |
| `devops-checkpoint/runtime/app.py` | Shared placeholder HTTP runtime copied into each independently built image. |

## Architecture Trace

The placeholder set follows the Architecture Checkpoint service/deployable names from `10-architecture-overview.md` and `11-bounded-context-architecture.md`. Data stores, Kafka/Event Log, and quota stores are not service placeholders because they are backing infrastructure, not independently delivered application services.

The fully wired service is `api-gateway-bff`, because the architecture makes it the public command/query entry point and the Client CLI can exercise it with a harmless `room list` or `whoami` style smoke command.

## Pipeline Narrative

Each service uses the same per-service spine:

`test -> build -> deliver -> deploy-staging -> integration-staging -> optional production`

All services are wired through `test`, `build`, and `deliver`. Exactly one service, `api-gateway-bff`, continues through `deploy-staging` and `integration-staging`.

Important mechanics:

- **Independent triggers:** every service fragment uses `rules:changes` scoped to `services/<service>`, `deploy/helm/<service>`, its CI fragment, and the shared runtime/template paths.
- **Fail fast:** downstream jobs use `needs`, so a failed test stops that service's build/deliver/deploy path.
- **One image per service:** every service has its own Dockerfile and produces `${CI_REGISTRY_IMAGE}/<service>:${CI_COMMIT_SHA}`.
- **Build once, promote by digest:** `deliver` pushes the image, extracts the registry digest, exports it through `deliver.env`, and Helm deploys the same digest to staging/prod.
- **One chart per service:** each service has a packageable chart under `deploy/helm/<service>`.
- **Contract seam:** `api-gateway-bff:contract` validates the OpenAPI JSON before build.

## Helm Choice

This checkpoint uses pipeline-applied **Helm** rather than GitOps. Helm is the better fit here because the assignment asks reviewers to see the stage spine directly in this single GitLab repo. GitOps would be a good production evolution, but it would add a second cluster-state repository and make the checkpoint harder to inspect. The design still keeps a GitOps-friendly shape: one chart per service, environment-specific values, and immutable image digest promotion.

Staging and production differ through `values-staging.yaml` and `values-production.yaml`: production raises replica counts/resources for HTTP edge services and sets `UNOARENA_ENVIRONMENT=production`. Secrets are not committed; Kubernetes access, registry credentials, external URLs, and the Client CLI path are GitLab protected variables or cluster integration settings.

## Staging Smoke

The deploy job for `api-gateway-bff` runs a real readiness gate:

`kubectl rollout status deployment/api-gateway-bff -n unoarena-staging --timeout=180s`

Only after that, `api-gateway-bff:integration-staging` runs `devops-checkpoint/smoke/api_gateway_bff_cli_smoke.py`. The smoke test is aligned with `Client-Checkpoint.md`: it invokes the team's canonical CLI entrypoint and does not assume any backend wire protocol.

- invokes the Client Checkpoint CLI from `UNOARENA_CLI`, defaulting to `client-checkpoint/unoarena`;
- injects the staging URL through `UNOARENA_API_URL` / `STAGING_BASE_URL`;
- runs the canonical `whoami` command by default; `UNOARENA_CLI_SMOKE_ARGS` can be set to another canonical command such as `room list`;
- accepts JSON, JSON-lines, or human-readable CLI output, then asserts a configured placeholder marker through `UNOARENA_SMOKE_EXPECT`;
- retries once, then fails the pipeline.

The smoke script does not call `curl` or the service directly. The placeholder app emits structured JSON logs for every request, so an operator can verify the smoke hit:

`kubectl logs deployment/api-gateway-bff -n unoarena-staging --tail=50`

## Rollback

Rollback path: run `helm rollback api-gateway-bff <previous-revision> -n unoarena-staging` (or the production namespace) to return to the previous chart revision and pinned image digest.

## Required CI Variables

| Variable | Scope | Purpose |
|---|---|---|
| `STAGING_BASE_URL` | staging | Public URL used by the Client CLI smoke test. |
| `PRODUCTION_BASE_URL` | production | Optional production environment URL. |
| `UNOARENA_CLI` | integration | Optional override for the Client Checkpoint CLI path. |
| `UNOARENA_CLI_SMOKE_ARGS` | integration | Canonical CLI command used by the smoke test, default `whoami`. |
| `UNOARENA_SMOKE_EXPECT` | integration | Comma-separated markers expected in CLI output, default `placeholder-player,api-gateway-bff`. |
| Kubernetes auth / GitLab agent settings | staging/prod | Allows `helm upgrade` and `kubectl rollout status`. |
| GitLab registry variables | built-in | `CI_REGISTRY`, `CI_REGISTRY_IMAGE`, `CI_REGISTRY_USER`, `CI_REGISTRY_PASSWORD`. |

## Coverage Matrix

| Service | Architecture area | test | build | deliver | deploy-staging | integration-staging | deliver-prod | deploy-prod |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `api-gateway-bff` | Edge | yes | yes | yes | yes | yes | manual | manual |
| `realtime-gateway` | Edge | yes | yes | yes | no | no | no | no |
| `identity-api` | Identity & Session | yes | yes | yes | no | no | no | no |
| `session-control-publisher` | Identity & Session | yes | yes | yes | no | no | no | no |
| `identity-audit-worker` | Identity & Session | yes | yes | yes | no | no | no | no |
| `room-command-api` | Room Gameplay | yes | yes | yes | no | no | no | no |
| `room-engine` | Room Gameplay | yes | yes | yes | no | no | no | no |
| `rng-deck-service` | Room Gameplay | yes | yes | yes | no | no | no | no |
| `room-timer-scheduler` | Room Gameplay | yes | yes | yes | no | no | no | no |
| `room-outbox-relay` | Room Gameplay | yes | yes | yes | no | no | no | no |
| `room-query-api` | Room Gameplay | yes | yes | yes | no | no | no | no |
| `room-creation-command-consumer` | Room Gameplay | yes | yes | yes | no | no | no | no |
| `room-log-replay-api` | Room Gameplay | yes | yes | yes | no | no | no | no |
| `tournament-api` | Tournament Orchestration | yes | yes | yes | no | no | no | no |
| `tournament-orchestrator` | Tournament Orchestration | yes | yes | yes | no | no | no | no |
| `round-kickoff-planner` | Tournament Orchestration | yes | yes | yes | no | no | no | no |
| `round-provisioning-workers` | Tournament Orchestration | yes | yes | yes | no | no | no | no |
| `room-result-consumer` | Tournament Orchestration | yes | yes | yes | no | no | no | no |
| `bracket-event-publisher` | Tournament Orchestration | yes | yes | yes | no | no | no | no |
| `ranking-api` | Ranking | yes | yes | yes | no | no | no | no |
| `rating-command-consumer` | Ranking | yes | yes | yes | no | no | no | no |
| `leaderboard-projection-workers` | Ranking | yes | yes | yes | no | no | no | no |
| `rating-audit-publisher` | Ranking | yes | yes | yes | no | no | no | no |
| `spectator-projection-ingestors` | Spectator View | yes | yes | yes | no | no | no | no |
| `public-room-view-api` | Spectator View | yes | yes | yes | no | no | no | no |
| `public-tournament-view-api` | Spectator View | yes | yes | yes | no | no | no | no |
| `spectator-stream-publisher` | Spectator View | yes | yes | yes | no | no | no | no |
| `projection-schema-guard` | Spectator View | yes | yes | yes | no | no | no | no |
| `audit-ingestor` | Compliance & Audit | yes | yes | yes | no | no | no | no |
| `dispute-replay-api` | Compliance & Audit | yes | yes | yes | no | no | no | no |
| `audit-export-worker` | Compliance & Audit | yes | yes | yes | no | no | no | no |

## Future Invariant Test Slots

These are not implemented against placeholders, but the pipeline shape has room for them without changing the service decomposition:

| Architecture invariant | Future job location |
|---|---|
| Log-before-broadcast | `room-command-api` / `room-outbox-relay` integration suite |
| Single-active-session push invalidation | `identity-api` + `realtime-gateway` integration suite |
| 5-second challenge and 60-second reconnect timers | `room-timer-scheduler` integration suite |
| Spectator privacy | `spectator-projection-ingestors` + `public-room-view-api` contract suite |
| Tournament round surge and advancement idempotency | `round-provisioning-workers` + `room-result-consumer` integration suite |
