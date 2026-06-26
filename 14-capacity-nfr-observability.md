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

### Storage growth estimates

These estimates are intentionally order-of-magnitude. They show that the architecture has a storage story for the same peak rates used above.

Assumptions:

- average committed gameplay event after envelope/index overhead: 1-2 KB
- public projection delta: 0.5-1 KB
- audit copy: 0.5-2 KB depending on whether it stores only hashes/reason codes or full high-stakes replay material
- peak gameplay event rate: 150,000-700,000 events/sec
- a mega-round peak is bursty; a 2-hour intense round is a more realistic stress window than 24 hours sustained at absolute peak

| Store / data class | Back-of-envelope growth | Architectural implication |
|---|---|---|
| Room Gameplay immutable log | 150k-700k events/sec * 1-2 KB = about 150 MB/sec to 1.4 GB/sec. If sustained for 24h, roughly 13-121 TB/day. A 2-hour mega-round is roughly 1-10 TB. | Hot event-log storage must be partitioned by `roomId` and tiered quickly after room completion. Cold replay goes to compressed object storage; active rooms stay in hot partitions. |
| Room outbox | Same event count but transient rows, roughly 0.5-1 KB each. At peak, 75-700 MB/sec if relay is delayed. | Outbox retention must be short, normally 24-72h after publish. It is not the long-term event store. Relay lag dashboards are capacity-critical. |
| Public room/spectator view store | 100,000 active room snapshots * 2-10 KB = about 200 MB-1 GB for room snapshots. Public deltas add a few GB to tens of GB during a mega-round, depending on retention window. | Public projections are cheap compared with authoritative logs; they can be rebuilt from public events and expired after room/tournament visibility windows. |
| Realtime connection registry | 1M-10M SSE connections * 0.5-2 KB metadata = about 0.5-20 GB distributed across gateway/registry shards. | Registry must be sharded and TTL-based; it is operational state, not historical data. |
| Tournament assignment manifests | 1,000,000 players plus 100,000 room assignments at tens to hundreds of bytes each = hundreds of MB to low GB per mega-tournament. | Store manifests in partitioned relational/object storage; archive after tournament completion and dispute window. |
| Ranking history | One record per rated player outcome. A 1M-player casual spike at 0.5-1 KB per player outcome is about 0.5-1 GB per full-room-result wave. | Ranking ledger growth is manageable but append-only; leaderboards are projections over the ledger. |
| Audit WORM | Normal mode stores sensitive subset and hashes: often 10-40% of gameplay log volume. High-stakes mode can approach full gameplay-log volume, about 1-10 TB for a 2-hour mega-round. | Audit retention must use object/WORM storage and hash-chain indexes; gameplay commands must not synchronously block on remote audit writes. |

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

### Partition and shard assumptions

The capacity numbers above translate to the following order-of-magnitude partitioning targets:

| Resource | Assumption | Rationale |
|---|---|---|
| Room Engine partitions/shard groups | Hundreds to low thousands of room shards, each owning many `RoomSession` actors | At 100,000 concurrent rooms, 500 shards means approximately 200 rooms per shard; each shard processes commands for its rooms sequentially by `roomId`, but shards run in parallel |
| Kafka partitions for `room.gameplay.public.v1` | Hundreds of partitions, keyed by `roomId` | At 150,000-700,000 events/sec, keeping per-partition throughput under a few thousand events/sec avoids consumer lag; `roomId` key preserves per-room ordering |
| Kafka partitions for `room.outcomes.v1` | Tens to low hundreds, keyed by `roomId` | Lower volume than gameplay events; round-end spikes are absorbed by independent consumer groups |
| Kafka partitions for `tournament.lifecycle.v1` | Tens, keyed by `tournamentId` | One active mega-tournament at a time; partitions mainly serve parallel consumer groups |
| Kafka partitions for `room.commands.v1` | Tens to hundreds, keyed by `roomId` | Must absorb 1,700-10,000 CreateRoom commands/sec during tournament kickoff; partition count matches provisioning worker parallelism |
| Realtime Gateway instances | Tens to hundreds of edge instances | At 1,000,000+ SSE connections, assuming 10,000-50,000 connections per gateway instance; regional edge pools for spectator scale |
| Room Timer Scheduler partitions | Tens, partitioned by `roomId` hash or timer bucket | Each partition scans due deadlines independently; total scan interval must stay well under 1 second for challenge window precision |

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
| Bracket/standings projection | normal p99 <= 5 seconds after tournament progression event; <= 2 minutes during mega-round completion spike while marked `updating` | partitioned projection workers, expected-room-count tracking, explicit projection status |
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
| Timers | due timers, late expiries, duplicate expiry suppression, reconnect vs expiry race outcomes, scheduler partition lag. Timer Scheduler workers are partitioned by `roomId` hash or timer bucket; each partition scans its deadline table independently. Expected tolerance: challenge expiry should be processed close to 5 seconds, but the Room Engine always verifies `expiresAt` against authoritative time before applying side effects, so a slightly late expiry command does not apply an incorrect penalty. A late-expiry metric tracks scheduler precision under load. |
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

## 6. Course best-practice review

The archive/course material highlights common patterns and anti-patterns. The architecture aligns as follows:

| Course pattern / risk | Architecture stance |
|---|---|
| Database per service | Each bounded context owns its persistence; no shared operational database is used |
| API Gateway / BFF | Public REST commands and SSE subscription setup pass through edge gateways |
| Event-driven communication | Cross-context facts use Kafka/event-log topics with partition keys, consumer groups, replay, and idempotent consumers |
| Saga over distributed transactions | Tournament advancement and room provisioning use an orchestrated saga/process manager; no 2PC-style distributed DB transaction |
| CQRS/read models | Spectator View, brackets, leaderboards, and public stats are projections, not authoritative write models |
| Anti-Corruption Layer | Spectator View and downstream consumers translate published events into local projection models instead of sharing Room Gameplay internals |
| Avoid distributed monolith | Services do not share DBs, do not require synchronous chains for core gameplay, and can scale independently |
| Avoid chatty microservices | Hot gameplay validation remains inside `RoomSession`; downstream effects use batched/event-driven propagation |
| Avoid event soup | Topics have named owners, allowed event types, idempotency keys, and versioned contracts |
| Observability | Correlation ids, causation ids, structured logs, lag metrics, and dashboards are defined for async flows |

## 7. Residual risks and explicit bounds

- Exact cloud sizing, instance types, and OS-level file descriptor tuning are intentionally out of scope, but the realtime tier is explicitly isolated so those concerns do not overload gameplay services.
- If spectator demand reaches the 10,000,000 connection worst case, capacity depends on regional realtime edges and quotas. This does not change gameplay correctness.
- If product later makes jump-in/stacking mandatory, Room Gameplay can enforce them inside the same sequence model; capacity assumptions may need higher per-room command burst margins.
- If course staff requires one physical pod per room, the same service contracts hold; the deployment scheduler simply maps each `RoomSession` actor to a dedicated Room Engine Pod instead of a shared shard pod.

## 8. Adaptive throttling degradation priority

When system pressure exceeds capacity (broker lag spikes, partition overload, or round kickoff surge), the architecture sheds load in the following priority order to preserve gameplay correctness:

| Priority | Category | Policy |
|---|---|---|
| 1 (highest) | Accepted gameplay command writes and room timers | Never shed. These are the core consistency path. Backpressure stops upstream command acceptance rather than dropping committed writes. |
| 2 | Tournament result intake and room provisioning | Preserve. Provisioning workers may be throttled or paced, but results are not dropped. DLQ absorbs poison messages. |
| 3 | Authenticated player SSE streams | Preserve where possible. Under extreme load, player streams may experience increased latency but are not terminated. |
| 4 (lowest) | Spectator streams, anonymous queries, analytics, bracket projections | Degrade first. Spectator subscriptions can be shed, rate-limited, or served stale snapshots. Analytics and leaderboard projections can lag. |

Concrete trigger examples:

| Signal | Threshold | Action |
|---|---|---|
| Realtime Gateway CPU or memory | > 80% for 5 minutes, or file descriptors > 85% capacity | Reject new anonymous spectator streams with `429` and `Retry-After`; preserve player streams |
| Public event/projection lag | `room.gameplay.public.v1` or `spectator.public-updates.v1` consumer lag p95 > 10 seconds | Switch spectators to snapshot refresh mode and reduce delta fan-out frequency |
| Broker lag on gameplay command/outcome topics | p95 lag > 2 seconds for `room.commands.v1` or `room.outcomes.v1` | Slow Round Provisioning Workers; do not drop committed outcomes |
| Room command p99 latency | > 250 ms for 5 minutes | Freeze new spectator subscriptions and non-critical analytics fan-out before throttling gameplay command acceptance |
| Timer scheduler late-expiry metric | p95 challenge expiry lateness > 500 ms | Prioritize timer partitions over projection workers and pause optional bracket refreshes |

This ensures gameplay remains correct and authoritative during surge pressure while allowing non-critical paths to degrade gracefully.
