# 03 — Aggregates, Entities, and Value Objects

## Aggregate design principles

This design uses aggregates to protect **business invariants that must hold immediately**. Read models, analytics, and ranking updates are intentionally outside these immediate consistency boundaries.

## Candidate aggregates

### A. RoomSession Aggregate
**Bounded context**: Room Gameplay  
**Why it is an aggregate root**  
All timing-sensitive rules in a room are strongly coupled:
- only one authoritative current turn
- only one legal active sequence
- Uno challenge windows are relative to turn progression
- disconnect timers affect turn-skipping and forfeits
- match progression depends on completed game outcomes
- room completion must be derived from authoritative room state

Because these decisions must be made atomically, `RoomSession` is the primary aggregate root for gameplay.

#### Contains
- room identity and type (`casual` or `tournament`)
- roster and seat assignments
- room lifecycle status
- active `MatchState`
- current authoritative room version / sequence
- active timers relevant to the room
- last accepted command identifiers for deduplication
- public/private projection markers

#### Key invariants
1. A room has exactly one lifecycle state at a time.
2. A room in `waiting` cannot accept gameplay commands.
3. A room in `completed` cannot mutate gameplay state.
4. Only seated players with a valid active session may issue gameplay commands.
5. Exactly one active turn exists when a game is in progress.
6. A command is applied only if its expected sequence matches the current room version.
7. No action may modify state after the room has completed.
8. A disconnecting player retains the same hand if they reconnect within 60 seconds.
9. If the disconnect window expires during that player's turn, forfeit is automatic.
10. Casual-room forfeit removes the player and the room continues if a valid competitive game remains.
11. Tournament-room forfeit eliminates the player from the match.
12. A room emits one authoritative completion outcome.

### B. Tournament Aggregate
**Bounded context**: Tournament Orchestration  
**Purpose**  
Owns the overall tournament identity, lifecycle, rule profile, and round progression policy. It should remain relatively small and delegate round-specific large-set membership to round aggregates.

#### Contains
- tournament id
- registration status
- tournament status
- advancement rule profile
- final-room threshold rule
- references to round aggregates
- finalized tournament placement outcome

#### Key invariants
1. A tournament has one active status at a time.
2. A tournament cannot start without a valid player set.
3. A tournament may have at most one active round at a time, unless the domain later permits staged overlap explicitly.
4. Once remaining players are 10 or fewer, the next gameplay allocation must create one final room.
5. A tournament cannot complete before the final room resolves.
6. A player cannot be both eliminated and advanced in the same tournament step.

### C. TournamentRound Aggregate
**Bounded context**: Tournament Orchestration  
**Purpose**  
Owns one elimination tier's active participants, room assignments, room completion tracking, and advancement decisions.

#### Contains
- round number
- eligible player set or partition references
- room assignment set
- room completion status per assigned room
- advancement decisions
- elimination decisions
- tie-break application records

#### Key invariants
1. A player may be assigned to exactly one room in a round.
2. Advancement is computed only from authoritative room result reports.
3. Advancement count per completed room is exactly 3 unless fewer remain by terminal tournament rules.
4. Tie-break order is:
   - higher match wins
   - lower cumulative card-point total
   - earliest final-game completion timestamp
5. A room result report for the same room and round is consumed idempotently.
6. A round completes only when all assigned rooms are resolved or marked with a terminal compensation decision.

### D. PlayerSession Aggregate
**Bounded context**: Identity & Session  
**Purpose**  
Protects single-active-session semantics and authenticated continuity.

#### Contains
- player id
- current active session id
- session state
- invalidation reason
- login version

#### Key invariants
1. A player has at most one active session.
2. A new login invalidates the previous active session immediately.
3. Commands from invalidated sessions are rejected.
4. Reconnect may resume gameplay only if both session validity and room reconnect window are satisfied.

### E. RatingProfile Aggregate
**Bounded context**: Ranking  
**Purpose**  
Owns player ratings and their authoritative histories.

#### Contains
- player id
- casual Elo
- tournament placement rating
- rating history entries
- processed outcome identifiers for idempotency

#### Key invariants
1. Casual Elo is updated only from completed casual games.
2. Tournament placement rating is updated only from tournament outcomes as defined by policy.
3. Abandoned games produce no Elo update.
4. The same game outcome cannot be applied twice to the same profile.

## Internal entities

### Inside RoomSession

#### Seat
Entity representing a player's stable position in a room.
- seat number
- player id
- seated status
- elimination/forfeit status within room
- public name reference

#### MatchState
Entity representing the series played inside a room.
- match id
- max games
- games completed
- per-player game wins
- cumulative card-point totals
- final advancement/placement summary

#### GameState
Entity representing one Uno game.
- game number within match
- player hands
- draw pile state reference
- discard stack
- current chosen color
- current direction
- active turn seat
- pending penalties
- challenge window state
- current turn timer state if applicable
- completed placement

#### DisconnectStatus
Entity/value hybrid tracking temporary absence.
- disconnected at
- reconnect deadline
- inactive vs restored state
- whether expiry occurred during turn

### Inside TournamentRound

#### RoomAssignment
- room id
- assigned players
- assignment status
- result report status

#### AdvancementDecision
- player id
- advancement rank within room
- reason
- tie-break path used

#### EliminationDecision
- player id
- elimination cause
- source room id

### Inside RatingProfile

#### RatingHistoryEntry
- outcome id
- previous rating
- new rating
- delta
- cause
- timestamp

## Value objects

### Shared value objects

**RoomId, TournamentId, RoundId, MatchId, GameId, PlayerId, SessionId**  
Strongly typed identifiers.

**RoomType**  
`casual | tournament`

**RoomStatus**  
`waiting | in_progress | completed`

**TournamentStatus**  
Examples: `scheduled | registration_open | in_progress | finalizing | completed | cancelled`

**RoundStatus**  
`preparing | active | awaiting_results | completed`

**SessionStatus**  
`active | invalidated | expired`

**ExpectedSequence**  
Command-side expected room version.

**CommandId / ActionId / ReportId**  
Idempotency identifiers.

**Card**
- color
- rank
- action type

**CardSet**
A collection of cards, typically a hand.

**DiscardStack**
Ordered public stack.

**DrawPileState**
Hidden pile state, possibly as an opaque deterministic reference rather than fully exposed collection outside the aggregate.

**Direction**
`clockwise | counterclockwise`

**UnoChallengeWindow**
- opened at
- expires at
- target player
- eligible challengers
- closure reason

**DisconnectWindow**
- disconnected at
- reconnect deadline
- expired boolean
- closure reason

**Placement**
An ordered finish position.

**MatchScore**
Wins per player plus tie-break support metrics.

**CardPointTotal**
Numeric value used in tournament tie-break.

**CompletionTimestamp**
Used in final-game completion tie-break.

**RateLimitDecision**
Though security-oriented, it can be modeled as a policy result value object consumed by command acceptance logic.

## Aggregate boundaries and why they matter

### Why not split GameState into its own aggregate?
Because legal action validation depends on tightly coupled room facts:
- whose turn it is
- whether a disconnect skip just occurred
- whether a challenge window is still open
- whether the match is already decided
- whether the room already completed

Splitting those into separate aggregates would move immediate consistency into asynchronous coordination, which is inappropriate for split-second gameplay rules.

### Why not model the whole Tournament as one aggregate?
Because 1,000,000-player tournaments make one giant consistency boundary both conceptually and operationally wrong. The tournament should define policy, while round aggregates hold independently progressing slices of state.

### Why are rankings eventually consistent?
Because gameplay correctness must never depend on whether the ranking side effect was already processed. Rating updates are a consequence of authoritative outcomes, not part of deciding them.

## Aggregate-to-aggregate references

- `RoomSession` references:
  - tournament id if tournament room
  - round id if tournament room
  - room ruleset profile
- `TournamentRound` references:
  - tournament id
  - room ids assigned to the round
- `RatingProfile` references:
  - processed game outcome ids, not mutable gameplay state
- `PlayerSession` references:
  - player id only; no gameplay state ownership
