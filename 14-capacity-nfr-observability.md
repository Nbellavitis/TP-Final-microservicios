# 14 - Capacity Sketch, NFRs, Threat Model, Observability, and ADRs

This document covers the mandatory capacity sketch from deliverable 6.5 and includes strongly recommended architecture artifacts.

## 1. Capacity sketch

### Official scale interpreted

The assignment calls out tournaments up to 1,000,000 players and a first-round surge of over 100,000 simultaneous matches/rooms. With rooms capped at 10 players:

- 1,000,000 active tournament players / 10 players per room = approximately 100,000 concurrent tournament rooms.
- Each tournament room plays a match of up to 3 games.
- The first round is a coordinated kickoff, not slow organic load.

### First-round assumptions

| Dimension | Order of magnitude used for architecture |
|---|---|
| Tournament players | 1,000,000 |
| Room size | up to 10 players |
| First-round active rooms/matches | 100,000 |
| Active player SSE streams | 1,000,000 |
| Spectator SSE streams | 1,000,000 ordinary first-round assumption; 10,000,000 worst-case multiplier if spectators average 10 per player |
| Room creation burst | 100,000 rooms over 10-120 seconds, depending on configured kickoff throttle |
| Accepted gameplay commands | roughly 30,000-100,000 commands/sec at peak across all rooms |
| Gameplay domain events | roughly 150,000-700,000 events/sec, assuming 3-7 events per accepted command |
| Round completion spike | 100,000 `RoomCompleted` events over seconds to minutes, with projection/analytics workers isolated from Room Gameplay writers |

These are sizing targets for architectural decomposition, not exact benchmark claims.

### Component scaling behavior

| Component | Scale model |
|---|---|
| API Gateway | horizontal; stateless except low-latency quota/session cache |
| Realtime Gateway | horizontal; connection-heavy; independent from Room Engine Pods; partitioned subscriptions by room/tournament |
| Room Engine Pods | horizontal by `roomId` ownership; one authoritative room actor/leader per active room; no global command lock |
| Room Timer Scheduler | partitioned by timer bucket/room id; stateless workers recover from durable deadlines |
| Room Outbox Relay | horizontal by outbox partition; preserves per-room order |
| Broker/event log | partitioned primarily by `roomId`, `tournamentId`, or `playerId` depending on topic |
| Tournament Orchestrator | one logical aggregate decision owner per tournament/round, with sharded provisioning/result workers for bulk work |
| Round Provisioning Workers | horizontal; throttled per tournament and per Room Gameplay partition |
| Ranking Workers | horizontal by `playerId` or rating batch id; idempotent source outcome processing |
| Spectator Projection | horizontal by `roomId` and `tournamentId`; does not push backpressure into Room Gameplay |
| Audit Ingestor | horizontal append pipeline; audit lag does not block source commits except for explicit high-stakes fail-closed policy |

### Round kickoff handling

The first-round surge is handled by sharded provisioning:

1. Tournament Orchestrator commits the round and assignment manifest.
2. Round Kickoff Planner splits approximately 100,000 room assignments into shards.
3. Provisioning workers process shards with concurrency limits.
4. Each room create command uses deterministic `roomId` and `assignmentId`.
5. Room Gameplay accepts duplicates idempotently and publishes `TournamentRoomReady`.
6. The orchestrator reconciles expected assignments against ready rooms.

If configured to complete kickoff in 60 seconds, the architecture must sustain about 1,700 room create attempts/sec. If configured for a 10-second aggressive kickoff, it must sustain about 10,000 room create attempts/sec. Backpressure can stretch kickoff slightly while preserving correctness; the requirement is coordinated readiness at scale, not one synchronous transaction.

### Round completion spike handling

Round end produces many `RoomCompleted` events close together. Room Gameplay writes are isolated because:

- completion events are committed to the room game log/outbox locally
- Tournament, Ranking, Spectator, and Audit consume asynchronously
- each consumer group has independent lag and DLQ
- Room Gameplay never waits for bracket projection or analytics writes

Tournament result consumers partition by `tournamentId:roundId:roomId`. A missing result keeps only the round closure waiting; it does not reopen completed rooms.

### Spectator fan-out

Spectators can outnumber players. Realtime Gateway and Spectator View therefore scale independently from Room Gameplay.

Mitigations:

- public spectator streams consume only sanitized projections
- room/tournament stream fan-out happens at realtime edges
- popular rooms can be replicated to regional edge gateways
- connection quotas protect gameplay from spectator floods
- if product policy allows, anonymous spectator streams can be capped or degraded before authenticated player streams

## 2. NFR matrix

| Flow | Target property | Architectural support |
|---|---|---|
| Gameplay command acceptance | low latency, strict correctness | REST to Room Command API, room actor routing, per-room optimistic append, idempotency |
| Stale command rejection | immediate conflict response | `expectedSequence` checked in Room Engine; `409` semantics and `StaleCommandRejected` |
| Realtime player updates | near realtime after durable commit | outbox relay to SSE gateway; per-room ordering by `roomSequence` |
| Spectator updates | scalable, privacy-safe | public CQRS projection and independent SSE fan-out |
| Tournament kickoff | high throughput, controlled surge | sharded assignment manifest, provisioning workers, deterministic room ids |
| Tournament advancement | correctness over speed | idempotent `RecordTournamentRoomResult`; no speculative advancement |
| Ranking updates | eventually consistent, exactly-once effect | source outcome dedupe, rating history ledger |
| Session replacement | prompt invalidation | session control topic to gateways plus session-version checks |
| Dispute replay | auditable and deterministic | immutable game log, RNG commitments, restricted replay API |
| Abuse resistance | layered throttling | edge, identity, user, room, tournament, realtime, adaptive limits |

## 3. Lightweight threat model

| Threat | Example | Mitigation |
|---|---|---|
| Spoofing | Player submits a command for another seat | Gateway validates token; Room Engine checks `playerId` against seat; emits `SessionMismatchDetected` |
| Tampering | Forged `RoomCompleted` sent to Tournament | signed/internal event transport, schema validation, producer ACLs, `UntrustedRoomResultRejected` |
| Repudiation | Player disputes a draw or penalty | immutable room game log, seeded RNG commitment, audit hash chain |
| Information disclosure | Spectator asks for hand contents | Spectator View has no hand data; private routes absent/denied; `SpectatorPrivacyViolationPrevented` |
| Denial of service | Spam `PlayCard` or open millions of SSE streams | layered rate limits, per-room quota, connection quotas, adaptive throttling |
| Elevation of privilege | Old session continues receiving room stream after new login | `PreviousSessionInvalidated` control topic closes old streams; commands verify session version |
| Event replay | Duplicate action or room result is replayed | idempotency keys: `actionId`, `roomCompletionEventId`, `sourceGameOutcomeId` |
| Projection poisoning | Public event accidentally includes private fields | schema allow-list and quarantine before writing Spectator View |

## 4. Observability architecture

### Correlation identifiers

Every command/event envelope should carry:

- `correlationId`
- `causationId`
- `eventId`
- source aggregate id (`roomId`, `tournamentId`, `playerId`)
- source version (`roomSequence`, `roundVersion`, `sessionVersion` where applicable)

### Key metrics

| Area | Metrics |
|---|---|
| Room Gameplay | command latency, accepted/rejected/stale/replay counts, sequence conflict rate, game log append latency, outbox lag, active room count |
| Timers | due timers, late expiries, duplicate expiry suppression, reconnect vs expiry race outcomes |
| Realtime | active SSE connections, per-room fan-out, dropped streams, session invalidation close latency, stream gap recovery |
| Tournament | assignments planned, rooms ready, provisioning DLQ count, outstanding room results, round closure lag |
| Ranking | rating request lag, dedupe count, failed/ignored abandoned outcomes |
| Spectator | projection lag, schema violations, snapshot refresh count |
| Audit | ingestion lag, hash validation failures, replay/export access count |
| Security/rate limiting | per-layer throttle counts, login failure rate, session mismatch count |

### Logs and traces

- Structured logs use the same correlation ids as events.
- Async traces connect command acceptance, outbox publish, consumer handling, and projection write through `correlationId`/`causationId`.
- Tournament round dashboards show kickoff progress and completion progress by shard.
- Room hot-path dashboards show stale command spikes and timer late-expiry spikes.

## 5. Architecture decision records

### ADR-001: REST commands plus SSE updates

Decision: Use REST for commands and SSE for realtime updates.

Reason: The problem statement already defines REST/SSE, and the domain has unidirectional state updates with immediate command validation needs.

Consequence: Long-lived connections are isolated in Realtime Gateway; Room Engine Pods stay CPU/rules focused.

### ADR-002: Event-sourced room log with transactional outbox

Decision: Room Gameplay appends authoritative events and outbox rows atomically.

Reason: The product definition requires every state change in the immutable game log before broadcast.

Consequence: Downstream delivery is at-least-once and idempotent, but no client sees unlogged state.

### ADR-003: RNG/Deck as an internal Room Gameplay service

Decision: Keep RNG/Deck deployable inside Room Gameplay rather than creating a new bounded context.

Reason: The approved design did not separate it as a bounded context, and deck decisions are part of authoritative gameplay.

Consequence: Architecture can scale RNG independently while keeping domain language and event ownership in Room Gameplay.

### ADR-004: First-class Spectator View

Decision: Materialize spectator projections from public events.

Reason: Spectator privacy is a core invariant and cannot rely on ad hoc transport filtering.

Consequence: Spectators may see slightly stale data, but they cannot read hidden hands or draw pile state.

### ADR-005: Durable timers for challenge and reconnect windows

Decision: Persist timer deadlines and process expiry through idempotent room commands.

Reason: 5-second and 60-second domain windows must survive process crashes and leader failover.

Consequence: Timer races are resolved by the same room sequence model as player actions.

### ADR-006: Sharded tournament provisioning

Decision: Start rounds by committing an assignment manifest and processing room creation through sharded workers.

Reason: 100,000 room creations cannot be a single synchronous loop inside the tournament aggregate.

Consequence: Kickoff is controllable, retryable, and observable; deterministic room ids make retries safe.

### ADR-007: Separate Ranking from Room Gameplay

Decision: Apply Elo/tournament ratings asynchronously in Ranking.

Reason: Rating updates are consequences of authoritative outcomes, not prerequisites for gameplay completion.

Consequence: Leaderboards may lag, but room completion remains correct and auditable.

### ADR-008: Per-context persistence

Decision: Avoid a single shared database.

Reason: Boundaries in the DDD design require independent ownership of hidden gameplay state, tournament decisions, ratings, sessions, and public projections.

Consequence: Integration uses published events and APIs; consumers must tolerate eventual consistency and duplicates.

## 6. Residual risks and explicit bounds

- Exact cloud sizing, instance types, and OS-level file descriptor tuning are intentionally out of scope, but the realtime tier is explicitly isolated so those concerns do not overload gameplay services.
- If spectator demand reaches the 10,000,000 connection worst case, capacity depends on regional realtime edges and quotas. This does not change gameplay correctness.
- If product later makes jump-in/stacking mandatory, Room Gameplay can enforce them inside the same sequence model; capacity assumptions may need higher per-room command burst margins.
- If course staff requires one physical pod per room, the same service contracts hold; the deployment scheduler simply maps each `RoomSession` actor to a dedicated Room Engine Pod instead of a shared shard pod.
