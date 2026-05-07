# 11 - Bounded Context Architecture

This document covers deliverable 6.1: each bounded context from the design package, its deployable services, public interfaces, async contracts, internal interfaces, and dependencies.

## 1. Identity & Session Context

### Purpose and scope

Identity & Session owns player identity, authentication, active session truth, session revocation, and the single-active-session rule.

It does not own room state, tournament eligibility rules beyond identity/account checks, gameplay reconnect windows, ranking, or public projections.

### Services

| Service | Responsibility |
|---|---|
| Identity API | Login, logout, token issuance, session validation, account/session queries for trusted services |
| Session Store | Strong active-session state by `playerId`, revoked token/session records, login version |
| Session Control Publisher | Publishes invalidation messages to gateways and other consumers after session changes |
| Identity Audit Worker | Copies security-sensitive identity facts into Compliance & Audit |

### Synchronous public interfaces

| Operation | Maps to design command/query | Auth expectations |
|---|---|---|
| `POST /v1/auth/login` | `LoginPlayer` | Public endpoint with credential validation and login throttling |
| `POST /v1/auth/logout` | `LogoutPlayer` | Requires active session token |
| `GET /v1/auth/session` | session query | Requires active session token |
| `POST /internal/sessions/validate` or gRPC `ValidateSessionForAction` | `ValidateSessionForAction` | Internal only, mTLS from gateways/services |
| `POST /internal/sessions/{sessionId}/invalidate` | `InvalidateSessionForSecurityReason` | Internal operator/security role only |

All public APIs are versioned under `/v1`. The stable player identity passed downstream is `playerId`; session ids are never trusted if they are only supplied by clients.

### Asynchronous contracts

| Topic | Producer | Consumers | Event types | Idempotency/correlation |
|---|---|---|---|---|
| `identity.session-events.v1` | Identity API | Audit, observability, optional fraud/risk consumers | `PlayerLoggedIn`, `PreviousSessionInvalidated`, `ActiveSessionIssued`, `SessionInvalidated`, `SessionClosed`, `SessionRejected`, `SessionMismatchDetected` | `sessionEventId`, `playerId`, `sessionVersion`, `correlationId` |
| `identity.session-control.v1` | Session Control Publisher | API Gateway, Realtime Gateway, Room Command API auth cache | `PreviousSessionInvalidated`, `SessionInvalidated` | key by `playerId`; consumers keep highest `sessionVersion` |

### Single-active-session runtime path

1. `LoginPlayer` locks the `PlayerSession` row for the player.
2. The previous active session is marked invalidated and a new `sessionVersion` is committed.
3. `PreviousSessionInvalidated` and `ActiveSessionIssued` are written to the outbox/session event feed.
4. `identity.session-control.v1` reaches all Realtime Gateway instances.
5. Gateways close or error the old player's SSE streams and clear subscription state.
6. Old REST commands fail at gateway/service validation because token session version no longer matches the active version.

This satisfies the assignment requirement that invalidation reaches the process that owns long-lived connections, not only the database.

### Dependencies

- Supplies canonical identity and session validity to Room Gameplay and Tournament Orchestration.
- Publishes invalidation to Realtime Gateway and API Gateway.
- Sends security facts to Compliance & Audit.

## 2. Room Gameplay Context

### Purpose and scope

Room Gameplay owns the authoritative `RoomSession`: lifecycle, seats, turn order, card legality, hidden hands, server-authoritative deck/RNG use, Uno challenge windows, reconnect windows, forfeits, match series state, game completion, match completion, and room completion.

It does not own tournament-wide seeding, global Elo formulas, identity issuance, or spectator public storage.

### Services

| Service | Responsibility |
|---|---|
| Room Command API | REST command boundary, request validation, auth/session checks, routing by `roomId`, sequence/idempotency envelope validation |
| Room Engine Pods | Authoritative `RoomSession` command handling, strict sequencing, rules enforcement, event sourcing/game log append, match progression |
| RNG/Deck Service | Internal deterministic shuffles/draws by seed and draw cursor; never exposed to clients |
| Room Timer Scheduler | Durable timer ownership for `UnoChallengeWindow` and `DisconnectWindow` deadlines |
| Room Outbox Relay | Publishes committed authoritative, public, outcome, timer, and audit events from the room outbox |
| Room Query API | Player-only snapshots and current state queries using authorized projection scopes |
| Room Log Replay API | Internal dispute/replay access to immutable game logs |

### Synchronous public interfaces

| Operation | Maps to design command | Auth expectations and main response |
|---|---|---|
| `POST /v1/rooms` | `CreateRoom` | Active player session; casual room creation only from public clients |
| `POST /v1/rooms/{roomId}/seats` | `SeatPlayerInRoom` | Active player session; validates player can occupy requested seat |
| `POST /v1/rooms/{roomId}/lock-roster` | `LockRoomRoster` | Room owner/system policy authorization |
| `POST /v1/rooms/{roomId}/matches` | `StartMatchInRoom` | Room owner/system policy authorization |
| `POST /v1/rooms/{roomId}/actions/play-card` | `PlayCard` | Seated player, active session, `Idempotency-Key`, `expectedSequence`; returns accepted state sequence or `409` for stale |
| `POST /v1/rooms/{roomId}/actions/draw-card` | `DrawCard` | Same command envelope |
| `POST /v1/rooms/{roomId}/actions/pass-turn` | `PassTurn` | Same command envelope |
| `POST /v1/rooms/{roomId}/actions/call-uno` | `CallUno` | Same command envelope |
| `POST /v1/rooms/{roomId}/actions/challenge-uno` | `ChallengeUno` | Same command envelope; challenger must be eligible |
| `POST /v1/rooms/{roomId}/reconnect` | `ReconnectPlayer` | Current active session for same `playerId`; reconnect deadline still open |
| `GET /v1/rooms/{roomId}` | player room snapshot query | Seated players only; returns only caller-authorized private state |

### Internal-only interfaces

| Operation | Maps to command/query | Caller |
|---|---|---|
| `POST /internal/rooms` | `CreateRoom` for tournament-bound rooms | Tournament Provisioning Workers |
| `POST /internal/rooms/{roomId}/disconnects` | `MarkPlayerDisconnected` | Realtime Gateway / session continuity worker |
| `POST /internal/rooms/{roomId}/timers/reconnect-expiry` | `ExpireReconnectWindow` | Room Timer Scheduler |
| `POST /internal/rooms/{roomId}/timers/challenge-expiry` | internal expiry leading to `UnoChallengeWindowClosed` | Room Timer Scheduler |
| `GET /internal/rooms/{roomId}/game-log` | immutable log query | Compliance & Audit, replay jobs, authorized operators |

### Asynchronous contracts

| Topic | Producer | Consumers | Event types | Payload ownership and idempotency |
|---|---|---|---|---|
| `room.lifecycle.v1` | Room Outbox Relay | Spectator Projection, Audit, Tournament Orchestration for readiness | `RoomCreated`, `RoomTypeAssigned`, `PlayerSeated`, `RoomRosterUpdated`, `RoomRosterLocked`, `RoomStarted`, `RoomCompleted`, `TournamentRoomReady` | Owned by Room Gameplay; keyed by `roomId`; event id + `roomSequence` |
| `room.gameplay.authoritative.v1` | Room Outbox Relay | Audit, replay/analytics jobs, restricted internal consumers | `MatchStarted`, `GameInitialized`, `InitialHandsDealt`, `TurnBegan`, `CardPlayed`, `ColorChosen`, `CardDrawn`, `TurnEffectApplied`, `UnoDeclared`, `PenaltyApplied`, `CardsPenaltyDrawn`, `TurnAdvanced`, disconnect/forfeit events | May include hidden card references or seed commitments where authorized; never consumed by Spectator View |
| `room.gameplay.public.v1` | Room Outbox Relay after public projection at write boundary | Spectator Projection, Realtime Gateway player public stream | Public envelopes of documented events such as `TurnBegan`, `CardPlayed`, `ColorChosen`, `UnoChallengeResolved`, `PlayerDisconnected`, `PlayerReconnected` | Whitelisted payload only; no hands, draw pile, future RNG, or session data |
| `room.outcomes.v1` | Room Outbox Relay | Tournament Result Consumer, Ranking, Audit, analytics | `GameCompleted`, `GameAbandoned`, `PlacementRecorded`, `CardPointTotalsRecorded`, `MatchScoreUpdated`, `MatchCompleted`, `RoomCompleted`, `EloUpdateRequested` | `sourceGameOutcomeId`, `roomCompletionEventId`, `roomType`, `outcomeKind`; dedupe by source id |
| `room.security.v1` | Room Outbox Relay | Audit, fraud/risk, observability | `StaleCommandRejected`, `ReplayCommandIgnored`, `IllegalMoveRejected`, `RateLimitTriggered`, `SpectatorPrivacyViolationPrevented`, `SecurityAuditRecorded` | command/action id and correlation id |

### Log-before-broadcast implementation

Room Engine Pods use an event-sourced write path:

1. Load `RoomSession` snapshot and log tail.
2. Validate `expectedSequence`, idempotency key, session-player-seat match, rules, and timers.
3. Append authoritative events to the immutable room game log.
4. Write outbox rows for internal authoritative events, public events, downstream outcome events, and audit copies in the same transaction.
5. Return command result after commit.
6. Room Outbox Relay publishes committed rows.

No realtime gateway, spectator projection, ranking worker, tournament worker, or audit ingestor consumes uncommitted in-memory state.

### Timer architecture

#### Uno challenge window

- Owner: Room Gameplay.
- Source fact: `UnoChallengeWindowOpened` with `challengeWindowId` and `expiresAt`.
- Durable state: the window is part of `GameState`; a timer row is also stored for scheduler scanning.
- Expiry: Room Timer Scheduler sends an internal expiry command. Room Engine emits `UnoChallengeWindowClosed` if the window is still open and no `TurnBegan` already closed it.
- Idempotency: `challengeWindowId` is unique inside the game. Duplicate expiry commands are ignored if the window is already closed.

#### Reconnect window

- Owner: Room Gameplay for gameplay consequences; Realtime Gateway detects connection loss.
- Source fact: `PlayerDisconnected` followed by `ReconnectWindowOpened`.
- Durable state: `DisconnectWindow` contains `reconnectDeadline`.
- Expiry: `ExpireReconnectWindow` emits `ReconnectWindowExpired`, `PlayerMarkedInactive`, and possibly `PlayerForfeited`.
- Idempotency: expiry command key is `roomId:playerId:disconnectWindowId`.

### Match series coordination

`MatchState` lives inside `RoomSession`. When `GameCompleted` is committed:

- Room Engine emits `MatchScoreUpdated`.
- If no player has reached the match-winning condition and `maxGames` remains, policy command `AdvanceMatchSeries` prepares the next game and emits `NextGamePrepared`, `GameInitialized`, `InitialHandsDealt`, and `TurnBegan`.
- If the series is terminal, Room Engine emits `MatchCompleted` and then `RoomCompleted`.

Tournament Orchestration never starts game 2 or game 3. It only consumes the room result after the room completes.

### Dependencies

- Customer of Identity & Session for active-session truth.
- Supplier to Tournament Orchestration, Ranking, Spectator View, and Compliance & Audit.
- Internally uses RNG/Deck Service as part of Room Gameplay, so no separate bounded context is introduced.

## 3. Tournament Orchestration Context

### Purpose and scope

Tournament Orchestration owns tournament lifecycle, registration, round creation, room assignment, advancement, elimination, final room creation, tournament completion, and tournament placement rating triggers.

It does not own in-room gameplay, card legality, hidden hands, casual Elo, or live session enforcement.

### Services

| Service | Responsibility |
|---|---|
| Tournament API | Tournament creation, registration, start commands, tournament administration |
| Tournament Orchestrator | `Tournament` and `TournamentRound` aggregate command handling, advancement decisions, final room trigger |
| Round Kickoff Planner | Builds sharded provisioning plans for very large rounds |
| Round Provisioning Workers | Idempotently request tournament-bound rooms in Room Gameplay |
| Room Result Consumer | Consumes `RoomCompleted`, calls `RecordTournamentRoomResult`, handles dedupe and DLQ |
| Bracket Event Publisher | Publishes public progression events to Spectator View and analytics |

### Synchronous public interfaces

| Operation | Maps to design command/query | Auth expectations |
|---|---|---|
| `POST /v1/tournaments` | `CreateTournament` | Admin/operator |
| `POST /v1/tournaments/{tournamentId}/registration:open` | `OpenTournamentRegistration` | Admin/operator |
| `POST /v1/tournaments/{tournamentId}/registrations` | `RegisterPlayerForTournament` | Active player session |
| `POST /v1/tournaments/{tournamentId}/registration:close` | `CloseTournamentRegistration` | Admin/operator |
| `POST /v1/tournaments/{tournamentId}:start` | `StartTournament` | Admin/operator, rate-limited, requires registration closed |
| `GET /v1/tournaments/{tournamentId}` | tournament query | Authenticated or public depending on tournament visibility |

Internal result intake is event-first, but an idempotent internal endpoint may exist for reconciliation:

| Operation | Maps to design command | Caller |
|---|---|---|
| `POST /internal/tournaments/{tournamentId}/rounds/{roundId}/room-results` | `RecordTournamentRoomResult` | Room Result Consumer / reconciliation job |
| `POST /internal/tournaments/{tournamentId}/rounds/{roundId}:close-and-prepare-next` | `CloseRoundAndPrepareNext` | Orchestrator policy worker |

### Asynchronous contracts

| Topic | Producer | Consumers | Event types | Idempotency/correlation |
|---|---|---|---|---|
| `tournament.lifecycle.v1` | Tournament Orchestrator | Spectator Projection, Audit, Ranking for placement trigger, analytics | `TournamentCreated`, `TournamentRegistrationOpened`, `PlayerRegisteredForTournament`, `TournamentRegistrationClosed`, `TournamentStarted`, `RoundCreated`, `RoundCompleted`, `FinalRoomRequired`, `FinalRoomCreated`, `TournamentPlacementsFinalized`, `TournamentCompleted` | `tournamentEventId`, `tournamentId`, `roundId`, `correlationId` |
| `tournament.round-assignments.v1` | Round Kickoff Planner | Round Provisioning Workers, Audit | `PlayersPartitionedIntoRooms`, `TournamentRoomProvisionRequested` | deterministic `assignmentId`, `roomId`, shard id |
| `room.commands.v1` | Round Provisioning Workers | Room Command API / Room creation workers | wrapped `CreateRoom` command for tournament-bound rooms | idempotent by deterministic `roomId` and `assignmentId` |
| `tournament.results.v1` | Tournament Orchestrator | Spectator Projection, Audit, Ranking placement trigger | `TournamentRoomResultRecorded`, `RoomAdvancementEvaluated`, `PlayersAdvanced`, `PlayersEliminated`, `TournamentPlacementRatingUpdateRequested` | dedupe by `roomCompletionEventId`; player decisions keyed by `tournamentId:roundId:playerId` |

### First-round surge mechanism

Round 1 for 1,000,000 players means approximately 100,000 tournament rooms when rooms are filled to 10 players. A single orchestrator transition must not synchronously create 100,000 rooms.

The mechanism is:

1. `StartTournament` commits `TournamentStarted`, `RoundCreated`, and a round provisioning plan.
2. Round Kickoff Planner creates deterministic assignment shards, for example by `hash(tournamentId, roundId, assignmentId)`.
3. `PlayersPartitionedIntoRooms` and many `TournamentRoomProvisionRequested` messages are published to partitioned queues.
4. Round Provisioning Workers consume shards in parallel and call Room Gameplay with deterministic `roomId`, `roundId`, `assignmentId`, `matchProfile=maxGames:3`.
5. Room Gameplay treats duplicate room creation as idempotent and emits `TournamentRoomReady`.
6. Tournament Orchestration tracks shard progress and room readiness, but failed shards do not block successful shards.

Partial failure handling:

- Duplicate create requests return the existing room.
- Poison assignment messages go to DLQ with `assignmentId`.
- Provisioning gaps are reconciled by comparing the committed assignment manifest against `TournamentRoomReady`.
- Backpressure is applied by limiting worker concurrency per tournament and per Room Gameplay partition.

### Advancement and tie-break enforcement

Tournament Orchestration owns the runtime application of the tournament advancement rule. `RoomSession` reports authoritative match facts, but `TournamentRound` decides advancement:

1. select the top 3 players in the room by match wins
2. if tied, prefer the lower cumulative card-point total in the tied games
3. if still tied, prefer the earliest final-game completion timestamp

The `RecordTournamentRoomResult` command stores the source `roomCompletionEventId`, the match wins, cumulative card-point totals, forfeit/elimination markers, and completion timestamps before emitting `RoomAdvancementEvaluated`, `PlayersAdvanced`, and `PlayersEliminated`. A duplicate room result cannot advance or eliminate a player twice.

When 10 or fewer players remain after a round, the same orchestrator emits `FinalRoomRequired` and provisions a single final room instead of a normal next elimination round.

### Dependencies

- Customer of Identity & Session for registration and admin authorization.
- Supplier to Room Gameplay for tournament-bound room creation commands.
- Customer of Room Gameplay for authoritative room outcomes.
- Supplier to Ranking for tournament placement rating triggers.
- Supplier to Spectator View and Compliance & Audit for public/audit progression.

## 4. Ranking Context

### Purpose and scope

Ranking owns `RatingProfile`, casual Elo, tournament placement rating, rating history, and idempotent rating application.

It does not decide gameplay legality, tournament advancement, or whether a game is abandoned. Those facts arrive from Room Gameplay or Tournament Orchestration.

### Services

| Service | Responsibility |
|---|---|
| Rating Command Consumer | Consumes rating request events and calls rating aggregate logic |
| Ranking API | Query ratings and leaderboard read models |
| Leaderboard Projection Workers | Build read-optimized leaderboards and public rating views |
| Rating Audit Publisher | Publishes `RatingHistoryRecorded` to audit |

### Synchronous public interfaces

| Operation | Maps to query | Auth expectations |
|---|---|---|
| `GET /v1/players/{playerId}/ratings` | rating profile query | Authenticated user or public visibility policy |
| `GET /v1/leaderboards/casual-elo` | casual Elo leaderboard query | Public or authenticated |
| `GET /v1/leaderboards/tournament-placement` | tournament placement leaderboard query | Public or authenticated |

Rating mutation is not exposed as a public command. It is driven by authoritative domain events.

### Asynchronous contracts

| Topic | Producer | Consumers | Event types | Idempotency/correlation |
|---|---|---|---|---|
| `room.outcomes.v1` | Room Gameplay | Rating Command Consumer | `EloUpdateRequested`; defensive consumption of `GameCompleted`/`GameAbandoned` for validation | `sourceGameOutcomeId`, `roomType`, `outcomeKind` |
| `tournament.results.v1` | Tournament Orchestration | Rating Command Consumer | `TournamentPlacementRatingUpdateRequested` | `sourceTournamentOutcomeId` |
| `ranking.rating-events.v1` | Ranking | Spectator Projection, Audit, analytics | `EloUpdated`, `TournamentPlacementRatingUpdated`, `RatingHistoryRecorded` | `ratingEventId`, processed source id |

### Elo scope enforcement

The Rating Command Consumer accepts `ApplyCasualGameOutcomeToRatings` only when:

- source room type is `casual`
- outcome is a valid `GameCompleted`
- source is not `GameAbandoned`
- the outcome id has not been processed

Tournament play never produces casual Elo. Abandoned casual games do not produce Elo changes.

### Player statistics and completion-spike handling

Ranking also owns player rating/statistics read models derived from completed casual game outcomes and tournament placement outcomes. It ingests `GameCompleted`/`EloUpdateRequested` bursts through a dedicated consumer group on `room.outcomes.v1`, partitioned by `sourceGameOutcomeId` for intake and by `playerId` for profile updates.

This pipeline is deliberately separate from Room Gameplay writers:

- Room Gameplay only appends to its game log and outbox.
- Ranking lag does not slow command acceptance or room completion.
- Projection workers dedupe by `sourceGameOutcomeId`.
- Leaderboard and player-stat views include a projection version and can be explicitly marked stale while the worker group catches up.

### Dependencies

- Downstream of Room Gameplay for casual outcomes.
- Downstream of Tournament Orchestration for tournament placement outcomes.
- Supplier to Spectator View for public rating/leaderboard projections.
- Supplier to Compliance & Audit for rating history.

## 5. Spectator View Context

### Purpose and scope

Spectator View owns public room snapshots, public match scoreboards, public tournament bracket views, and spectator streams. It enforces privacy at projection and query time.

It does not own gameplay decisions, hidden state, tournament authority, or identity/session issuance.

### Services

| Service | Responsibility |
|---|---|
| Spectator Projection Ingestors | Consume public room/tournament/ranking events and materialize public views |
| Public Room View API | Query public room snapshots |
| Public Tournament View API | Query bracket/progression views |
| Spectator Stream Publisher | Feeds Realtime Gateway with public deltas by room/tournament |
| Projection Schema Guard | Rejects malformed public events containing disallowed private fields |

### Public interfaces

| Operation | Maps to design query/command | Auth expectations |
|---|---|---|
| `GET /v1/spectator/rooms/{roomId}` | public room snapshot query / `PublishPublicRoomSnapshot` result | Spectator token or anonymous policy if allowed |
| `GET /v1/spectator/rooms/{roomId}/events` | SSE subscription to public room stream | Token scopes checked by Realtime Gateway |
| `GET /v1/spectator/tournaments/{tournamentId}/bracket` | public bracket query / `PublishBracketProjection` result | Tournament visibility policy |
| `GET /v1/spectator/tournaments/{tournamentId}/events` | SSE subscription to public tournament stream | Token scopes checked by Realtime Gateway |

Any attempted private-hand spectator query is rejected and recorded as `SpectatorPrivacyViolationPrevented`.

### Asynchronous contracts

| Topic | Producer | Consumers | Event types | Privacy rule |
|---|---|---|---|---|
| `room.gameplay.public.v1` | Room Gameplay | Spectator Projection | public envelopes for `RoomCreated`, `PlayerSeated`, `RoomRosterLocked`, `GameInitialized`, `TurnBegan`, `CardPlayed`, `ColorChosen`, `UnoChallengeResolved`, `PlayerDisconnected`, `PlayerReconnected`, `GameCompleted`, `MatchScoreUpdated`, `RoomCompleted` | No hand contents, draw pile order, hidden RNG, session ids, or internal fraud data |
| `tournament.lifecycle.v1` and `tournament.results.v1` | Tournament Orchestration | Spectator Projection | `TournamentStarted`, `RoundCreated`, `PlayersAdvanced`, `PlayersEliminated`, `RoundCompleted`, `FinalRoomCreated`, `TournamentCompleted` | Only public bracket/progression data |
| `ranking.rating-events.v1` | Ranking | Spectator Projection | `EloUpdated`, `TournamentPlacementRatingUpdated` where public | Public rating deltas only |
| `spectator.public-updates.v1` | Spectator Projection | Realtime Gateway | `PublicRoomSnapshotPublished`, `BracketProjectionUpdated` | Already sanitized; keyed by room/tournament |

### Projection model

Spectator View uses CQRS:

- It consumes public events keyed by `roomId` or `tournamentId`.
- It stores a snapshot plus an ordered delta cursor.
- Realtime streams serve the snapshot and then deltas.
- If a gap is detected, the stream refreshes from the latest public snapshot.

Privacy is enforced before data is written to the Public View Store and again at API serialization.

### Bracket/read-model spike handling

At round end, Spectator View may receive a burst of `GameCompleted`, `MatchCompleted`, `RoomCompleted`, `PlayersAdvanced`, and `PlayersEliminated` facts. Projection workers consume these through independent consumer groups partitioned by `tournamentId` and `roundId`.

Coherence rules:

- per-room public deltas are applied in `roomSequence`
- tournament bracket updates are applied by `roundVersion` or tournament event version
- duplicate `RoomCompleted` or advancement events are ignored by source event id
- public bracket views can show an `updating` marker until all expected room results for the round have projected
- acceptable read-model staleness is seconds to low minutes during the largest completion spikes, but authoritative tournament closure remains in Tournament Orchestration

### Dependencies

- Downstream of Room Gameplay, Tournament Orchestration, and Ranking.
- Supplier to Realtime Gateway for spectator SSE delivery.
- Sends privacy violations and projection schema violations to Compliance & Audit.

## 6. Compliance & Audit Context

### Purpose and scope

Compliance & Audit owns immutable recordkeeping for dispute-oriented and security-sensitive decisions. It provides authorized replay/export APIs without becoming the primary decision-maker for gameplay, tournament, ranking, or identity.

### Services

| Service | Responsibility |
|---|---|
| Audit Ingestor | Consumes sensitive domain events and validates signatures/hash chain metadata |
| Tamper-Evident Audit Store | Append-only event storage, hash-chain records, WORM/object archive |
| Dispute Replay API | Authorized access to room logs, RNG commitments, penalties, forfeits, and placement history |
| Audit Export Worker | Controlled exports for compliance or instructor/operator review |

### Interfaces

| Operation | Purpose | Auth expectations |
|---|---|---|
| `GET /internal/audit/rooms/{roomId}` | Query audit index for a room | Compliance/operator role, mTLS |
| `GET /internal/audit/rooms/{roomId}/game-log-export` | Export immutable game log for dispute review | Break-glass or explicit dispute role |
| `POST /internal/audit/replay-jobs` | Start automated replay verification | Internal replay service only |

### Asynchronous contracts

| Topic | Producer | Consumers | Event types |
|---|---|---|---|
| `audit.domain-events.v1` | Room Gameplay, Tournament Orchestration, Identity & Session, Ranking, Spectator View | Audit Ingestor | signed/tamper-evident copies of shuffles/draws, penalties, forfeits, session invalidations, rating updates, advancement decisions, projection violations |

### Dependencies

- Downstream of every sensitive context.
- Authorized reader of Room Gameplay immutable game logs through Room Log Replay API.
- Does not mutate gameplay, tournament, session, or rating state.
