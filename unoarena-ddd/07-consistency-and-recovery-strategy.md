# 07 — Consistency and Recovery Strategy (Domain Level)

This document focuses on **business-level consistency**, not infrastructure internals.

## 1. Consistency strategy by context

### Room Gameplay
**Consistency model**: strong immediate consistency inside each room session

Reason:
- turn ownership
- legal card play
- Uno challenge timing
- disconnect skip/forfeit rules
- match progression

These rules cannot be left to eventual reconciliation without breaking core gameplay truth.

### Tournament Orchestration
**Consistency model**: strong consistency within each tournament round aggregate, eventual consistency from room result intake

Reason:
- round advancement must be correct
- but room results arrive asynchronously from many independent room sessions

### Ranking
**Consistency model**: eventual consistency with idempotent application

Reason:
- rating mutation is downstream of authoritative game completion

### Spectator View
**Consistency model**: eventual consistency, public-only projections

Reason:
- projection latency must not affect authoritative gameplay

### Identity & Session
**Consistency model**: immediate consistency for active-session truth

Reason:
- commands must know whether the current session is allowed to act

---

## 2. How invariant violations are prevented

## A. Sequence-based optimistic concurrency for room actions
Every gameplay command carries:
- room id
- player/session identity
- expected room sequence
- command/action id

The room accepts only if:
1. session is valid
2. player owns the acting seat
3. expected sequence equals current room version
4. action is legal in the current state

This prevents:
- stale writes
- out-of-order writes
- concurrent illegal wins

## B. Idempotency keys
Every meaningful externally visible mutation has a dedupe key.

Examples:
- gameplay action id
- tournament room result id
- rating source outcome id
- login attempt id

This prevents:
- duplicate card plays
- double advancement
- double Elo application

## C. Derived outcomes only from authoritative upstream events
Tournament and Ranking do not recreate gameplay truth.  
They consume already-authoritative room outcomes.

This prevents:
- divergent interpretation of the same room result
- multiple consumers calculating incompatible standings

## D. Public/private event split
Spectator-facing events are a separate domain contract from authoritative internal gameplay events.

This prevents:
- accidental exposure of private hands or hidden deck order

---

## 3. Detection of invariant violations

When prevention fails or suspicious data appears, the domain records explicit violations.

### Examples
- same idempotency key with different payload
- invalid room result signature or source trust failure
- impossible turn order
- public event containing private fields
- ranking update for an abandoned game
- duplicate advancement for one player in a round

### Typical events
- `SecurityAuditRecorded`
- `PublicProjectionSchemaViolationDetected`
- `UntrustedRoomResultRejected`
- `SuspiciousReplayDetected`
- `InvariantViolationDetected`

The guiding rule is: **do not silently repair domain corruption**. Detect, reject, quarantine, and preserve an audit trail.

---

## 4. Retries and deduplication

## A. Retry policy at business level
Retries are valid for downstream consequence processing:
- tournament result consumption
- ranking update
- public projection refresh
- audit write propagation

Retries are **not** valid for replaying a gameplay action as a new action if the original command may already have been accepted. That requires idempotent replay under the same action id.

## B. Deduplication decision table

| Situation | Business response |
|---|---|
| Same action id, same payload | return prior outcome |
| Same action id, different payload | reject and audit |
| Same room result id consumed twice | ignore duplicate |
| Same rating source outcome twice | ignore duplicate |
| Same login attempt retried | return prior session result if still valid |

---

## 5. Compensation and saga decisions

## A. Room completion -> Tournament progression
This is a saga-like business flow:

1. room completes authoritatively
2. tournament records the room result
3. tournament computes advancement/elimination
4. round closes when all rooms resolved
5. next round or final room is created

### Compensation stance
Do **not** compensate by reopening completed room gameplay.  
If downstream progression fails, retry the downstream step. The room result remains source truth.

## B. Room completion -> Ranking update
1. room/game completes
2. ranking update requested
3. rating profiles updated exactly once

### Compensation stance
Do not reverse the room result if rating update is delayed.  
Only compensate if a later discovered invalid source outcome is formally revoked by a separate administrative domain process.

## C. Session replacement during active play
1. new login invalidates old session
2. old session actions are rejected
3. player may reconnect under the new session if room reconnect window allows

### Compensation stance
No rollback of session invalidation. Identity truth is canonical.

---

## 6. Recovery decisions for important failure modes

### Missing tournament room result
- round remains open
- system retries result delivery/consumption
- reconciliation can request authoritative room completion record
- no speculative advancement

### Ranking consumer outage
- pending updates remain unapplied
- leaderboards may lag
- gameplay correctness remains unaffected

### Spectator projection loss
- recover from latest sanitized snapshot plus subsequent public events
- never rebuild public state from raw hidden data without the same privacy filter

### Disconnect timer expiry race
If reconnect and expiry arrive close together:
- authoritative ordering by room sequence/time decision decides the winner
- only one terminal truth is committed:
  - either `PlayerReconnected`
  - or `PlayerForfeited`

---

## 7. Business-level recovery principles

1. **Never sacrifice gameplay truth to preserve downstream convenience.**
2. **Never infer hidden state in downstream contexts.**
3. **Never double-apply the same consequence.**
4. **Never reopen a completed room just because a subscriber failed.**
5. **Prefer explicit rejection and audit over silent correction.**
6. **Keep private/public boundary enforced at the event contract itself.**

---

## 8. Where eventual consistency is acceptable

It is acceptable for these to lag:
- global leaderboard refresh
- bracket read model refresh
- spectator projection refresh
- audit copy propagation
- tournament placement rating update

It is **not** acceptable for these to lag:
- turn ownership
- legality of a card play
- whether challenge window is still open
- whether a session is active
- whether a player already forfeited
- whether room completion has already occurred
