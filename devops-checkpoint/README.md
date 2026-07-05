# DevOps Checkpoint - UnoArena

This checkpoint proves that the architecture decomposition can be built, delivered, and deployed independently. The services are intentionally placeholders: they expose `/health`, return canned JSON, and do not implement real Uno gameplay.

Scope clarification from the teaching staff: this delivery is the basic project pipeline scaffold. It must run test, build, and package/deliver stages, while deploy remains a placeholder. No running Kubernetes cluster, cloud account, or kubeconfig is required for this checkpoint.

Green pipeline run: **pending after first push to GitLab**. Paste the GitLab pipeline URL here once `api-gateway-bff:integration-staging` has passed in placeholder mode on the submission branch.

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

All services are wired through `test`, `build`, and `deliver`. Exactly one service, `api-gateway-bff`, continues through `deploy-staging` and `integration-staging` as the scaffold demonstrator. Per the scope clarification, those deploy and smoke jobs validate the wiring and print the Kubernetes/CLI operations that would be executed later; they do not require a live cluster.

Important mechanics:

- **Independent triggers:** every service fragment uses `rules:changes` scoped to `services/<service>`, `deploy/helm/<service>`, its CI fragment, and the shared runtime/template paths.
- **Fail fast:** downstream jobs use `needs`, so a failed test stops that service's build/deliver/deploy path.
- **Test hygiene:** each service runs its placeholder unit test, and the shared runtime is syntax-checked with `python -m py_compile`.
- **One image per service:** every service has its own Dockerfile and produces `${CI_REGISTRY_IMAGE}/<service>:${CI_COMMIT_REF_SLUG}-${CI_COMMIT_SHORT_SHA}`.
- **Build once, promote by digest:** `deliver` pushes the image, extracts the registry digest, exports it through `deliver.env`, and the placeholder deploy jobs carry that same digest forward to staging/prod.
- **One chart per service:** each service has a packageable chart under `deploy/helm/<service>`.
- **Contract seam:** `api-gateway-bff:contract` validates the placeholder OpenAPI contract before build.
- **Deploy placeholder:** `api-gateway-bff:deploy-staging` verifies image/chart metadata and echoes the exact Helm command and readiness gate that would be used once a cluster is introduced.

For every service in the coverage matrix, the repository mapping is deterministic:

| Item | Convention |
|---|---|
| Source path | `services/<service>/` |
| Pipeline fragment | `.gitlab/ci/services/<service>.yml` |
| Helm chart path | `deploy/helm/<service>/` |
| Image name | `${CI_REGISTRY_IMAGE}/<service>:${CI_COMMIT_REF_SLUG}-${CI_COMMIT_SHORT_SHA}` |
| Helm release | `<service>` |

Fail-fast is enforced with `needs`: `build` needs `test` (and, for `api-gateway-bff`, also `contract`), `deliver` needs `build`, `deploy-staging` needs `deliver`, and `integration-staging` needs `deploy-staging`. Retries are bounded to one runner/system retry in the root default and do not hide assertion failures. A future cross-service schema check would be modeled the same way as `api-gateway-bff:contract`: affected services depend on the shared contract job before build.

## Helm Choice

This checkpoint uses **Helm charts as the deployable model** rather than GitOps. Helm is the better fit here because the assignment asks reviewers to see the stage spine directly in this single GitLab repo. GitOps would be a good production evolution, but it would add a second cluster-state repository and make the checkpoint harder to inspect. The design still keeps a GitOps-friendly shape: one chart per service, environment-specific values, and immutable image digest promotion.

Staging and production differ through `values-staging.yaml` and `values-production.yaml`: production raises replica counts/resources for HTTP edge services and sets `UNOARENA_ENVIRONMENT=production`. Secrets are not committed; registry credentials are GitLab built-ins, and future external URLs or CLI overrides would be GitLab protected variables.

For this checkpoint the pipeline packages Helm charts and the deploy jobs are placeholders. They validate the delivered image digest and chart artifact, then print the `helm upgrade --install` command and the `kubectl rollout status` readiness gate that would be enabled in the next development phase. This satisfies the requested scaffold without provisioning infrastructure.

All placeholder charts use `ClusterIP` by default. Exposing `api-gateway-bff` through an Ingress or LoadBalancer is a future runtime concern, not part of this checkpoint scaffold.

## Staging Smoke

The deploy job for `api-gateway-bff` is intentionally a placeholder. It prints the future readiness gate:

`kubectl rollout status deployment/api-gateway-bff -n unoarena-staging --timeout=180s`

Only after that placeholder job succeeds, `api-gateway-bff:integration-staging` runs `devops-checkpoint/smoke/api_gateway_bff_cli_smoke.py`. In CI it runs with `UNOARENA_SMOKE_DRY_RUN=true`, so it verifies the smoke harness shape and prints the Client CLI command that would be executed against staging. This matches the professor's clarification that no real deploy is required.

- defaults to the Client Checkpoint CLI path `client-checkpoint/unoarena`;
- prints the canonical `whoami --json` command by default;
- receives the placeholder staging URL emitted by `deploy-staging`;
- can be switched to real CLI execution later by setting `UNOARENA_SMOKE_DRY_RUN=false` and providing a real `UNOARENA_API_URL` or `STAGING_BASE_URL`;
- when real mode is enabled, consumes JSON or JSON-lines output and asserts a configured placeholder marker through `UNOARENA_SMOKE_EXPECT`.

The smoke script does not call `curl` or the service directly. Once a real cluster is introduced, the placeholder app emits structured JSON logs for every request, so an operator can verify the smoke hit with:

`kubectl logs deployment/api-gateway-bff -n unoarena-staging --tail=50`

## Rollback

Future rollback path after real deploy is enabled: run `helm rollback api-gateway-bff <previous-revision> -n unoarena-staging` (or the production namespace) to return to the previous chart revision and pinned image digest.

## Required CI Variables

| Variable | Scope | Purpose |
|---|---|---|
| `UNOARENA_SMOKE_DRY_RUN` | integration | Defaults to `true` in CI so the Client CLI smoke remains a scaffold placeholder. |
| `STAGING_BASE_URL` | future staging | Optional real staging URL if dry-run is disabled later. |
| `PRODUCTION_BASE_URL` | future production | Optional production environment URL if production deploy is enabled later. |
| `UNOARENA_CLI` | future integration | Optional override for the Client Checkpoint CLI path when dry-run is disabled. |
| `UNOARENA_CLI_SMOKE_ARGS` | integration | Canonical CLI command used by the smoke test, default `whoami --json`. |
| `UNOARENA_SMOKE_EXPECT` | integration | Comma-separated markers expected in CLI output, default `placeholder-player,api-gateway-bff`. |
| GitLab registry variables | built-in | `CI_REGISTRY`, `CI_REGISTRY_IMAGE`, `CI_REGISTRY_USER`, `CI_REGISTRY_PASSWORD`. |

## Coverage Matrix

| Service | Architecture area | test | build | deliver | deploy-staging | integration-staging | deliver-prod | deploy-prod | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `api-gateway-bff` | Edge | yes | yes | yes | yes | yes | manual | manual | Fully wired scaffold; deploy and smoke are placeholders. |
| `realtime-gateway` | Edge | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `identity-api` | Identity & Session | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `session-control-publisher` | Identity & Session | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `identity-audit-worker` | Identity & Session | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `room-command-api` | Room Gameplay | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `room-engine` | Room Gameplay | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `rng-deck-service` | Room Gameplay | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `room-timer-scheduler` | Room Gameplay | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `room-outbox-relay` | Room Gameplay | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `room-query-api` | Room Gameplay | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `room-creation-command-consumer` | Room Gameplay | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `room-log-replay-api` | Room Gameplay | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `tournament-api` | Tournament Orchestration | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `tournament-orchestrator` | Tournament Orchestration | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `round-kickoff-planner` | Tournament Orchestration | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `round-provisioning-workers` | Tournament Orchestration | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `room-result-consumer` | Tournament Orchestration | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `bracket-event-publisher` | Tournament Orchestration | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `ranking-api` | Ranking | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `rating-command-consumer` | Ranking | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `leaderboard-projection-workers` | Ranking | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `rating-audit-publisher` | Ranking | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `spectator-projection-ingestors` | Spectator View | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `public-room-view-api` | Spectator View | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `public-tournament-view-api` | Spectator View | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `spectator-stream-publisher` | Spectator View | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `projection-schema-guard` | Spectator View | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `audit-ingestor` | Compliance & Audit | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `dispute-replay-api` | Compliance & Audit | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |
| `audit-export-worker` | Compliance & Audit | yes | yes | yes | no | no | no | no | Minimum checkpoint scaffold. |

## Future Invariant Test Slots

These are not implemented against placeholders, but the pipeline shape has room for them without changing the service decomposition:

| Architecture invariant | Future job location |
|---|---|
| Log-before-broadcast | `room-command-api` / `room-outbox-relay` integration suite |
| Single-active-session push invalidation | `identity-api` + `realtime-gateway` integration suite |
| 5-second challenge and 60-second reconnect timers | `room-timer-scheduler` integration suite |
| Spectator privacy | `spectator-projection-ingestors` + `public-room-view-api` contract suite |
| Tournament round surge and advancement idempotency | `round-provisioning-workers` + `room-result-consumer` integration suite |
