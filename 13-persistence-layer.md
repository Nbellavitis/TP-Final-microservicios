# 13 - Persistence Layer Per Context

This document covers deliverable 6.4: primary stores, consistency model, read models, retention, audit, and data ownership per context.

## 1. Persistence principles

- Each bounded context owns its operational data and schema.
- Cross-context communication uses APIs and events, not shared tables.
- Strong consistency is used only where domain invariants require it.
- Read models are rebuilt from published events where possible.
- Immutable game logs and audit trails are append-only.

## 2. Identity & Session

### Primary store

Recommended store class: relational database plus low-latency session cache.

Owned data:

- player account identity
- password/credential references or external identity provider links
- active `PlayerSession`
- `sessionVersion`
- revoked sessions and invalidation reasons
- login attempt ids and security audit references

### Consistency model

Strong per-player consistency. `LoginPlayer` locks or conditionally updates the active session row so that a player has at most one active session.

Transaction boundary:

- invalidate previous active session
- issue new active session
- write session outbox/control event

The session cache is a derived accelerator and may lag briefly, but active session truth is the store plus session-version control topic.

### Read models and caches

- API Gateway auth cache keyed by session id and session version, with short TTL.
- Realtime Gateway subscription/session registry, invalidated by `identity.session-control.v1`.

### Retention and audit

Session invalidations, suspicious login attempts, session mismatches, and security-triggered revocations are copied to Compliance & Audit. PII is kept in Identity; downstream events use stable ids and avoid leaking credentials or device details unless explicitly authorized.

## 3. Room Gameplay

### Primary store

Recommended store class: partitioned event store or relational append-only log with optimistic concurrency, plus snapshots.

Owned data:

- immutable game log per `roomId`
- `RoomSession` snapshots
- current room version / `roomSequence`
- command idempotency records by `roomId:actionId`
- hidden hands and draw pile state or opaque deterministic draw cursor
- match series state
- durable timer deadlines
- outbox rows

### Consistency model

Strong immediate consistency inside one `RoomSession`.

Authoritative transaction boundary for a gameplay command:

1. validate session, seat, expected sequence, idempotency, and legality
2. append one or more domain events to the game log
3. update room snapshot/current sequence if snapshots are used
4. store idempotency result
5. store timer rows to open/close windows as needed
6. write outbox rows

All of the above commits atomically. No broadcast is produced from memory before this commit.

### Log-before-broadcast storage shape

A practical schema can be:

| Table/stream | Purpose | Key constraints |
|---|---|---|
| `room_event_log` | immutable authoritative gameplay events | unique `(room_id, room_sequence)`, unique `event_id`, append-only |
| `room_snapshot` | latest compact aggregate snapshot | one row/doc per room with version |
| `room_command_dedupe` | action id -> accepted/rejected command result | unique `(room_id, action_id)` |
| `room_timer_deadline` | persisted challenge/reconnect deadlines | unique `timer_id`; indexed by `expires_at` |
| `room_outbox` | committed messages awaiting publish | unique `outbox_id`; status pending/published/quarantined |

The outbox row references committed log event ids. The relay cannot publish an event that is not in `room_event_log`.

### Read models

- Player room snapshot: built from authoritative state but scoped to the seated player. It may include that player's hand and public room state.
- Public room snapshot: produced through the public projection path and does not include hidden state.
- Operator/replay snapshot: internal, audited access only.

### Timer persistence

Challenge and reconnect deadlines are persisted as room state plus scheduler rows. A scheduler worker can die without losing the deadline because it is not the owner of truth; it is only a delivery mechanism for an expiry command.

### Retention and audit

The immutable game log is retained long enough to support dispute resolution, replay, and high-stakes tournament audit. Tournament and cash-prize tier logs should be retained according to compliance policy; casual logs may have shorter retention if product policy allows, but rating-affecting outcome events and audit hashes must remain.

### Game log read path for dispute resolution

Authorized consumers:

- Compliance & Audit Dispute Replay API
- automated replay verification jobs
- restricted operators during an approved dispute

Access controls:

- internal mTLS
- role-based authorization
- reason code and dispute id for exports
- access logged to Compliance & Audit
- no direct database access by support staff

Allowed purposes:

- reconstructing a game
- verifying server-authoritative RNG commitments and draw order
- investigating penalties, forfeits, stale command disputes, or tournament advancement disputes

The replay API can export authoritative events and seed commitments, but player private hand data is not exposed outside approved dispute scopes.

## 4. Tournament Orchestration

### Primary store

Recommended store class: relational database partitioned by `tournamentId` and `roundId`, plus large assignment manifests in object/document storage if needed.

Owned data:

- `Tournament`
- `TournamentRound`
- registration state
- round assignment manifests
- room readiness state
- room result receipts
- advancement and elimination decisions
- final room and tournament placement records
- provisioning shard state and DLQ references

### Consistency model

Strong within one `Tournament` or `TournamentRound` aggregate decision. Eventual from Room Gameplay result delivery.

Transaction boundaries:

- `StartTournament`: commit tournament status, round creation, and provisioning plan metadata
- `RecordTournamentRoomResult`: commit one room result receipt and derived advancement/elimination decisions for that room
- `CloseRoundAndPrepareNext`: commit round closure and next-round/final-room decision

Room creation itself is not inside the same transaction as tournament aggregate state; it is a saga step driven by idempotent provisioning commands.

### Read models

- Tournament bracket read model for users/spectators.
- Round progress dashboard for operators.
- Assignment readiness projection for detecting provisioning gaps.

These are eventually consistent and may lag authoritative tournament state by seconds during massive spikes.

### Retention and audit

Tournament registration, assignment, advancement, elimination, tie-break application, final placements, and provisioning decisions are retained for audit. The assignment manifest is important because it proves each player was assigned to exactly one room in a round.

## 5. Ranking

### Primary store

Recommended store class: relational database for rating profiles and rating history, plus cache/search store for leaderboards.

Owned data:

- `RatingProfile`
- casual Elo
- tournament placement rating
- rating history entries
- processed source outcome ids
- leaderboard projection state

### Consistency model

Strong within one player's rating profile update, eventual from upstream outcomes.

For a rating request:

1. verify source type and outcome eligibility
2. check processed source id
3. compute delta
4. update rating profile
5. append rating history entry
6. write outbox event

Multi-player Elo calculation can be coordinated by a rating update batch keyed by `sourceGameOutcomeId`, then applied to each involved `RatingProfile` idempotently.

### Read models

- casual Elo leaderboard
- tournament placement leaderboard
- player rating history view

Leaderboards are read optimized and may be stale while consumers catch up. The authoritative record is the rating profile and history ledger.

### Retention and audit

Rating history is durable and append-only from the application perspective. `RatingHistoryRecorded`, `EloUpdated`, and `TournamentPlacementRatingUpdated` are copied to Compliance & Audit.

## 6. Spectator View

### Primary store

Recommended store class: key-value/document store for public room snapshots and bracket documents, plus stream/delta cursor storage.

Owned data:

- public room snapshot by `roomId`
- public room delta cursor
- public match scoreboard
- public tournament bracket view
- public ranking snippets if displayed
- projection offsets by source topic/partition

### Consistency model

Eventual consistency. Spectator View must never be used as authority for gameplay, tournament advancement, or ranking.

Projection transaction boundary:

- consume source event
- validate public schema
- apply event to public snapshot/delta store
- commit projection offset
- publish `PublicRoomSnapshotPublished` or `BracketProjectionUpdated` when appropriate

If a projection event fails schema validation because it contains private fields, the event is quarantined and no public view update is written.

### Read models

- snapshot + delta stream for rooms
- snapshot + delta stream for tournament brackets
- optional leaderboard snippets

Staleness target is low, but stale public views do not affect gameplay truth.

### Privacy retention

Spectator View intentionally does not store:

- private hand identities
- hidden draw pile order
- session ids
- future RNG outcomes
- private fraud/risk details

If a field is not in the allow-list, it does not enter this store.

## 7. Compliance & Audit

### Primary store

Recommended store class: append-only/WORM object storage for event bodies plus indexed metadata in a relational or search store.

Owned data:

- audit event records
- hashes/signatures
- source event ids
- replay/export job records
- access logs for audit queries
- incident/quarantine records

### Consistency model

Eventually consistent copy of source domain truth. Audit must be durable and tamper-evident, but it does not block gameplay command commits unless a specific compliance mode requires fail-closed behavior for high-stakes rooms.

### Read models

- room dispute index
- tournament advancement audit index
- session/security audit index
- rating history audit index

### Retention

Audit retention should be longest for tournament/high-stakes rooms and security-sensitive events. PII boundaries remain in Identity; audit events should store only needed identifiers, hashes, and reason codes unless an approved dispute export requires more.

## 8. Cross-context data ownership summary

| Data | Owner | Other contexts receive |
|---|---|---|
| Player account and active session | Identity & Session | player id, session validity/version, invalidation events |
| Hidden hands, draw pile, room sequence | Room Gameplay | public projections or authorized audit/replay data only |
| Tournament assignment and advancement | Tournament Orchestration | public bracket events, rating placement triggers, audit records |
| Casual Elo and placement rating | Ranking | public leaderboard/rating events, audit records |
| Public room and bracket view | Spectator View | SSE/public query responses |
| Dispute trail and replay exports | Compliance & Audit | authorized internal reports, never primary mutation commands |

## 9. Multi-region note

The design can be deployed regionally by pinning each active `RoomSession` to one authoritative region/partition. Realtime gateways may exist globally, but commands for a room route to the room's owning partition. Cross-region read models can lag; the room command path must not split a single room's sequence authority across regions.
