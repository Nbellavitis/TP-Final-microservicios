# 12 - Communication Patterns and Integration View

This document covers deliverable 6.3: client connection model, rate limiting, and the explicit integration table.

## 1. Client connection model

UnoArena uses the model stated in the original problem definition:

- REST for client commands.
- SSE for realtime updates to players and spectators.

REST remains appropriate because commands such as `PlayCard`, `DrawCard`, `CallUno`, `ChallengeUno`, and tournament registration require immediate validation, idempotency keys, authentication, and conflict responses. SSE remains appropriate because gameplay updates are server-to-client streams; clients do not need bidirectional realtime frames for domain actions.

### Connection termination

Long-lived SSE connections terminate at the Realtime Gateway, not inside Room Engine Pods.

Player stream examples:

- `GET /v1/rooms/{roomId}/events`
- `GET /v1/tournaments/{tournamentId}/events`

Spectator stream examples:

- `GET /v1/spectator/rooms/{roomId}/events`
- `GET /v1/spectator/tournaments/{tournamentId}/events`

### Per-room ordering

Room Gameplay publishes committed events with:

- `roomId`
- `roomSequence`
- `eventId`
- `occurredAt`

Broker partitions and gateway stream buffers are keyed by `roomId`. The gateway only emits room deltas in ascending `roomSequence`. If it detects a gap, it fetches a fresh snapshot from the relevant player or public projection and resumes from the next cursor.

### Session invalidation and live streams

Identity & Session publishes `PreviousSessionInvalidated` and `SessionInvalidated` on `identity.session-control.v1`. Realtime Gateway instances consume this control topic and close matching SSE streams. Gateway auth caches also track `sessionVersion`, so a stale stream cannot keep receiving updates indefinitely if a push message is delayed.

### Spectator privacy

Spectators subscribe only to Spectator View projections. They never subscribe to `room.gameplay.authoritative.v1` and never receive player private hand payloads. Player streams can include private deltas only for the authenticated seated player; spectators use separate route prefixes and separate projection storage.

### Player-private realtime delivery

Players need private hand updates that spectators must never see. The architecture addresses this through a dedicated topic and gateway filtering:

1. The Room Engine transaction writes authoritative log events plus outbox rows for public deltas and per-player private deltas in the same commit.
2. The Player Stream Projector produces events on `room.gameplay.player-private.v1`, keyed by `roomId`. Each event carries a `recipientPlayerId` field.
3. The Realtime Gateway subscribes to `room.gameplay.player-private.v1` only after token/session validation and emits events exclusively where `recipientPlayerId` matches the active session principal.
4. Spectator View remains exclusively on `room.gameplay.public.v1` and has no access to the player-private topic.

Private deltas include:

- the card identity a player drew (`CardDrawnPrivate`)
- the player's own current hand after a draw, penalty, or initial deal (`HandUpdated`, `InitialHandDealt`)
- a private correction snapshot after reconnect (`ReconnectSnapshotPrivate`)
- a private rejection/reconciliation response if the player's local state is stale (`StaleStateCorrection`)

### Presence and disconnect detection

SSE is server-to-client, so detecting a client disconnect requires explicit architectural support. The Realtime Gateway maintains a **Realtime Connection Registry** with durable or replicated records:

| Field | Purpose |
|---|---|
| `sessionId` | Active session identifier |
| `playerId` | Canonical player identity |
| `roomId` | Room the player stream is connected to |
| `connectionId` | Unique stream connection identifier |
| `lastSeenAt` | Last successful heartbeat or data write timestamp |
| `sessionVersion` | Validates against Identity session truth |

Disconnect detection mechanism:

1. The Realtime Gateway periodically writes SSE heartbeat comments (`:heartbeat`) to each player stream, for example every 5 seconds. A failed write (TCP close, broken pipe) marks the connection as dead.
2. Optionally, active players send a lightweight REST heartbeat (`POST /v1/rooms/{roomId}/heartbeat`) that updates `lastSeenAt`, but all gameplay commands remain REST-based.
3. When the last active player gameplay connection for a given `playerId:roomId` pair is gone or stale for 10 seconds past `lastSeenAt`, the gateway calls `MarkPlayerDisconnected` on Room Command API.
4. A **Session Continuity Worker** runs independently every 5 seconds and reconciles gateway crashes by scanning the Connection Registry for stale records (where `lastSeenAt` exceeds the 10-second threshold and no active connection exists). It issues idempotent `MarkPlayerDisconnected` commands for any orphaned entries.
5. Multiple tabs or connections for the same `playerId:roomId` are tracked as separate `connectionId` entries. `MarkPlayerDisconnected` fires only when the last one is lost.

Normal maximum detection latency is therefore about 15 seconds after the last successful heartbeat/write. To preserve the domain rule, Room Gameplay records `disconnectedAt = lastSeenAt` and computes `reconnectDeadline = lastSeenAt + 60 seconds`, not "command arrival time + 60 seconds." If the detection command arrives late and the deadline is already past, the same room sequence can immediately emit `ReconnectWindowExpired` and the relevant forfeit events idempotently.

This makes the 60-second reconnect window operationally credible across gateway restarts, network partitions, and half-open TCP sockets.

## 2. Rate limiting architecture

Rate limiting is multi-layered. It is applied after enough identity information is available for user-scoped limits, but before expensive command execution.

| Layer | Deployable | Scope | Identity/scope source | Example behavior |
|---|---|---|---|---|
| Edge network/IP | API Gateway / Realtime Gateway | per IP, CIDR, ASN, unauthenticated login path | request IP and edge metadata | Throttle credential stuffing, connection floods, anonymous spectator floods |
| Auth/session | Identity API | per account, per login attempt, per active session churn | credentials, `playerId`, `loginAttemptId` | Slow repeated login failures; audit suspicious session replacement |
| User command | API Gateway / BFF | per authenticated `playerId` and endpoint | validated token claims plus session version | Reject spammy command bursts before routing to Room Gameplay |
| Room action | Room Command API | per `playerId:roomId:actionType` and per `roomId` | gateway-signed principal, path `roomId`, command type | Protect hot rooms from move spam and stale-command flooding |
| Tournament action | Tournament API | per `playerId:tournamentId` and admin operation | gateway-signed principal, path `tournamentId` | Protect registration, start, and administrative operations |
| Realtime connection | Realtime Gateway | per session, per room subscription, per spectator account/IP | token claims, room/tournament subscription scope | Limit concurrent SSE streams and subscription churn |
| Adaptive infrastructure | Gateway, Room Command API, Tournament Provisioning Workers | broker lag, partition overload, round kickoff pressure | internal metrics and quota store | Shed low-priority spectator subscriptions or slow provisioning workers before gameplay writes fail |

Shared token buckets or leaky buckets may use Redis or another low-latency quota store. Domain-significant throttling produces `RateLimitTriggered`; pure edge drops may remain operational metrics unless security policy requires audit.

## 3. Contract conventions

### REST conventions

REST APIs use `/v1` versioning and explicit HTTP semantics:

- `201 Created` for newly created resources when creation completes synchronously
- `200 OK` for completed command/query responses
- `202 Accepted` when work was durably accepted for asynchronous processing
- `400 Bad Request` for malformed commands
- `401 Unauthorized` for missing/invalid authentication
- `403 Forbidden` for authenticated principals lacking permission
- `409 Conflict` for stale `expectedSequence` or aggregate-version conflict
- `429 Too Many Requests` for rate-limit decisions

Mutating endpoints use `Idempotency-Key`. Gameplay mutation endpoints also require `expectedSequence`. Query/list endpoints should use cursor pagination when result sets can grow, especially tournament brackets, player lists, and audit queries.

Sync service calls use deadlines/timeouts and circuit breakers. A slow dependency must not create an unbounded synchronous call chain.

### Async event conventions

Published events use a CloudEvents-style envelope so consumers get consistent metadata independent of broker technology:

```json
{
  "specversion": "1.0",
  "id": "event-id",
  "source": "room-gameplay",
  "type": "RoomCompleted.v1",
  "subject": "room/{roomId}",
  "time": "2026-05-16T21:00:00Z",
  "datacontenttype": "application/json",
  "correlationId": "flow-id",
  "causationId": "previous-command-or-event-id",
  "data": {}
}
```

The `type` field preserves the documented domain event name from `04-commands-and-domain-events.md`, plus a schema version. Topic names provide the broader channel boundary, for example `room.outcomes.v1`.

Async contracts should be documented with AsyncAPI-style channel definitions or an equivalent schema registry:

- channel/topic name
- producer
- allowed event types
- payload owner
- partition key
- idempotency key
- retry/DLQ policy
- backward-compatibility rules

Schema evolution is additive by default. Consumers must tolerate unknown fields and must not depend on private producer storage schemas.

### Schema registry operating model

Each producing bounded context owns the schemas for the events it publishes. For example, Room Gameplay owns `room.*` schemas, Tournament Orchestration owns `tournament.*`, and Ranking owns `ranking.*`.

Operationally:

- every schema change is submitted with the service change that produces it
- CI runs an AsyncAPI/schema-registry compatibility check against the latest registered schema before merge
- compatible additive changes may stay on the same `.v1` topic/event type
- breaking changes require a new event type or topic version, such as `RoomCompleted.v2` or `room.outcomes.v2`, plus a migration/dual-publish window
- consumer contract tests pin the minimum schema version they understand
- the architecture/platform review role owns registry policy, while producer teams own the actual domain payloads

## 4. Integration table

| From | To | Pattern and contract | Rationale / traceability | Failure semantics |
|---|---|---|---|---|
| Player client | API Gateway -> Room Command API | REST command: `PlayCard`, `DrawCard`, `PassTurn`, `CallUno`, `ChallengeUno`; headers include `Idempotency-Key` and `expectedSequence` | Maps to design commands 5-9; immediate validation and `409` stale response required | Client retries with same `actionId`. Room Engine dedupes accepted/rejected result. Stale commands emit `StaleCommandRejected`. |
| Player client | API Gateway -> Room Command API | REST command: `CreateRoom`, `SeatPlayerInRoom`, `LockRoomRoster`, `StartMatchInRoom`, `ReconnectPlayer` | Maps to design commands 1-4 and 11 | Duplicate room/seat/start/reconnect requests return prior result when idempotency key matches. |
| API Gateway | Identity API / auth cache | Sync request/response or signed token introspection for `ValidateSessionForAction`; deadline + circuit breaker | Room/Tournament commands depend on active session truth | If Identity is temporarily unavailable, gateway may use a very short-lived signed session cache; high-risk commands can fail closed. |
| Identity API | Realtime Gateway | Pub/sub control topic `identity.session-control.v1` carrying `PreviousSessionInvalidated`, `SessionInvalidated` | Required live single-active-session invalidation path | Gateway closes old streams. If missed, replay/heartbeat session-version check closes them later. Highest `sessionVersion` wins. |
| Realtime Gateway | Room Command API | Internal REST command `MarkPlayerDisconnected` when the last player gameplay stream/heartbeat is lost | Maps to command 10 and events `PlayerDisconnected`, `ReconnectWindowOpened` | Duplicate disconnects dedupe by `disconnectWindowId`. If gateway crashes, session continuity worker reconciles missing disconnects. |
| Room Timer Scheduler | Room Engine Pod | Internal command for challenge expiry, resulting in `UnoChallengeWindowClosed` | Durable 5-second Uno challenge window | Duplicate expiry ignored if window already closed by `TurnBegan` or prior expiry. Scheduler recovers from persisted deadlines. |
| Room Timer Scheduler | Room Engine Pod | Internal command `ExpireReconnectWindow` | Maps to command 12 and events `ReconnectWindowExpired`, `PlayerMarkedInactive`, `PlayerForfeited` | Races with `ReconnectPlayer` are serialized by room sequence. Duplicate expiry is ignored. |
| Room Engine Pod | RNG/Deck Service | Internal sync RPC at `GameInitialized` or reshuffle to generate and persist a complete deterministic deck commitment by seed; not called per-draw. Deadline + circuit breaker. | Supports server-authoritative seeded deck without exposing hidden state. Keeps RNG off the per-action hot path after game initialization. | If RPC fails before `GameInitialized` commit, game init fails/retries. Once deck commitment and shuffled sequence are committed, each draw advances a persisted cursor inside the room transaction without further RNG calls. Audit stores deck commitment and seed for later replay verification. |
| Room Engine Pod | Game Log + Outbox | Single local transaction: append domain events and outbox rows | Implements log-before-broadcast for every authoritative state change | Crash before commit publishes nothing. Crash after commit leaves relay to publish pending outbox rows. |
| Room Outbox Relay | Event Log / Broker | Transactional outbox relay to `room.lifecycle.v1`, `room.gameplay.authoritative.v1`, `room.gameplay.public.v1`, `room.outcomes.v1`, `room.security.v1` | Fan-out without coupling downstream availability to gameplay writes | At-least-once publish. Consumers dedupe by `eventId` and `roomSequence`. Failed rows are retried; poison rows go to DLQ after quarantine. |
| Event Log | Realtime Gateway player streams | Pub/sub consumption of committed room public/player-authorized events | Delivers SSE updates without burdening Room Engine Pods | If gateway lags, clients can resubscribe with last event id and fetch snapshot. Gameplay continues. |
| Event Log | Spectator Projection Ingestors | Pub/sub from `room.gameplay.public.v1`, `tournament.lifecycle.v1`, `tournament.results.v1` | First-class public CQRS projection required by design | Projection lag does not affect gameplay. Malformed public payloads are rejected and audited. |
| Spectator Projection | Realtime Gateway spectator streams | Read model + stream cursor via `spectator.public-updates.v1` | Prevents spectators from touching authoritative hidden state | If projection is unavailable, spectator stream degrades or reconnects from last public snapshot; no hidden data fallback is allowed. |
| Tournament API | Tournament Orchestrator | Sync command handling for `CreateTournament`, `RegisterPlayerForTournament`, `StartTournament` | Tournament lifecycle requires immediate policy validation | Commands are idempotent by request id. Start is guarded by tournament aggregate version. |
| Tournament Orchestrator | Round Kickoff Planner / Provisioning Workers | Saga/process manager; async sharded work messages carrying `PlayersPartitionedIntoRooms` and `TournamentRoomProvisionRequested` | Handles 100k first-round room provisioning without one synchronous choke point | Workers publish idempotent `CreateRoom` command envelopes to `room.commands.v1` by `assignmentId`/`roomId`; Room Creation Command Consumer processes them inside Room Gameplay. Failed shards go to DLQ and reconciliation compares manifest to ready rooms. |
| Round Provisioning Workers | Room Gameplay (via `room.commands.v1`) | Primary async command topic for tournament-bound room creation; `CreateRoom` envelopes with deterministic `roomId` and `assignmentId` | Maps tournament assignments to Room Gameplay while preserving Room authority; avoids synchronous REST fan-out | Duplicate creates are idempotent by `roomId`. Backpressure limits per Room partition. Internal REST endpoint (`POST /internal/rooms`) retained only for reconciliation/repair. |
| Room Outbox Relay | Tournament Room Result Consumer | Pub/sub `room.outcomes.v1` carrying `RoomCompleted` for tournament rooms | Maps to `RecordTournamentRoomResult`; Tournament consumes authoritative match facts | At-least-once delivery. TournamentRound dedupes by `roomCompletionEventId`; missing results keep round open. |
| Room Outbox Relay | Ranking Consumer | Pub/sub `EloUpdateRequested` for non-abandoned casual games | Maps to `ApplyCasualGameOutcomeToRatings`; preserves Elo scope | Ranking dedupes by `sourceGameOutcomeId`; abandoned/tournament outcomes are ignored/audited if received. |
| Tournament Orchestrator | Ranking Consumer | Pub/sub `TournamentPlacementRatingUpdateRequested` | Maps to `ApplyTournamentPlacementOutcome`; separate from casual Elo | Dedupes by `sourceTournamentOutcomeId`; delayed rating does not block tournament completion. |
| Room/Tournament/Identity/Ranking/Spectator | Compliance & Audit | Pub/sub `audit.domain-events.v1`; restricted pull/export APIs for game log | Immutable dispute and security history | Audit lag never changes source truth. Invalid signatures/hash chain failures quarantine records and alert operators. |
| Compliance & Audit | Room Log Replay API | Internal sync query for immutable room game log | Supports dispute replay and RNG verification | mTLS/RBAC required. Access is logged. Source Room log remains immutable. |

## 5. Saga and process manager boundaries

### Room completion to tournament advancement

This is an orchestrated saga owned by Tournament Orchestration:

1. Room Gameplay emits `RoomCompleted`.
2. Room Result Consumer calls `RecordTournamentRoomResult`.
3. `TournamentRound` records result idempotently and emits `PlayersAdvanced` and `PlayersEliminated`.
4. When all room assignments are terminal, the orchestrator emits `RoundCompleted`.
5. It either creates the next round or emits `FinalRoomRequired` and provisions the final room.

There is no compensation that reopens a completed room. Recovery retries downstream progression.

### Room completion to ranking update

This is an eventually consistent consequence:

1. Room Gameplay emits `EloUpdateRequested` only for valid non-abandoned casual games.
2. Ranking applies `ApplyCasualGameOutcomeToRatings` exactly once.
3. Ranking emits `EloUpdated` and `RatingHistoryRecorded`.

If Ranking is down, gameplay remains complete and rating workers catch up later.

### Domain timers

The challenge and reconnect timers are not in-memory sleeps. They are durable deadlines owned by Room Gameplay and recovered by Room Timer Scheduler. Timer expiry commands are ordinary idempotent commands against `RoomSession`, which keeps the race resolution in the same sequencing model as player actions.

## 6. Contract ownership

- Room Gameplay owns gameplay event payloads and room outcome payloads.
- Tournament Orchestration owns tournament lifecycle and advancement payloads.
- Ranking owns rating payloads.
- Identity & Session owns session event/control payloads.
- Spectator View owns public projection payloads.
- Compliance & Audit owns audit export schemas, not source domain event meaning.

Consumers conform to the producer's published language and use anti-corruption logic when mapping into local read models.
