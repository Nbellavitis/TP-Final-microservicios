# 08 — Open Questions and Assumptions

This document explicitly separates **validated requirements** from **assumptions** introduced to complete the domain model under the assignment's scope constraints.

## 1. Validated requirements from the statement

The following are treated as validated because they were explicitly required:

- Rooms support 2 to 10 players.
- Tournaments can scale up to 1,000,000 players.
- Room lifecycle includes `waiting -> in_progress -> completed`.
- All random card generation is server-side and auditable.
- Every state change is appended to an immutable game log before broadcast.
- Actions are submitted through REST.
- Clients and spectators receive updates through SSE.
- Stale actions are rejected with a conflict-style semantic.
- Uno call rules include:
  - declaration required after second-to-last card
  - challenge allowed within 5 seconds
  - challenge window closes when next turn begins
  - loser of the challenge draws 2 cards
- Disconnect policy includes:
  - 60-second reconnect window
  - turn skipped during reconnect window
  - no bot substitution
  - forfeit if the window expires during the player's turn
- Tournament rooms play best-of-three matches.
- Top 3 advance from a tournament room.
- Tie-break order:
  1. match wins
  2. lower cumulative card-point total
  3. earliest final-game completion
- When 10 or fewer players remain, a final room is created.
- Casual rooms affect global Elo; tournament play does not.
- Abandoned games do not affect Elo.
- Single-active-session per player is required.
- Spectators must never see private hands.

---

## 2. Explicit assumptions

These assumptions were introduced to make the model behavior-complete.

### A. Casual room format assumption
**Assumption**  
A casual room is modeled as a room session whose match profile has `maxGames = 1`.

**Why**
This unifies room behavior while preserving the assignment's strict distinction between game and match.

**Impact if changed**
If casual rooms later support rematches or multi-game sessions, only the match profile changes; the aggregate boundary can remain the same.

---

### B. Public hand counts assumption
**Assumption**  
Spectator View may expose player hand counts as public state, but never card identities.

**Why**
In many card-game domains hand counts are public, but the assignment only explicitly guarantees player names and discard stack as public.

**Impact**
This should be validated with course staff or product owner. If rejected, hand counts must be removed from the public contract without changing room authority.

---

### C. Ruleset variability assumption
**Assumption**  
Optional rules such as stacking or jump-in are not globally enabled by default and must be explicit room ruleset options.

**Why**
The prompt mentions them as examples of high-concurrency mechanics, but does not say they are always active.

**Impact**
If the official product requires them globally, they become part of the base ruleset rather than optional policy.

---

### D. Tournament advancement count with heavy forfeits
**Assumption**  
A room may advance fewer than 3 players only if there are fewer than 3 valid competitors left by terminal state.

**Why**
The stated rule says top 3 advance, but severe forfeit scenarios require a terminal interpretation.

**Impact**
Needs validation if the desired business rule is “always produce 3 advancing slots” via fallback or bye logic.

---

### E. Manual resolution fallback assumption
**Assumption**  
If tie-break rules still fail to separate players after the specified three criteria, the domain raises an explicit unresolved-tie condition for manual or separately defined resolution.

**Why**
The prompt defines only three tie-breakers and no fourth rule.

**Impact**
A later validated deterministic tie-break can replace manual resolution cleanly.

---

### F. Session replacement reconnect assumption
**Assumption**  
If a player's old session is invalidated by a new login, the player may still resume an in-progress room under the new session, provided the room reconnect window remains open.

**Why**
This best satisfies both single-active-session control and gameplay continuity.

**Impact**
If prohibited, new login during active gameplay would effectively force immediate disconnect continuation and likely eventual forfeit.

---

### G. No speculative tournament progression assumption
**Assumption**  
Tournament Orchestration never advances players without authoritative room results.

**Why**
It preserves correctness and auditability.

---

## 3. Connection-semantics assumptions allowed by scope

The assignment allows assumptions about connection semantics without designing the protocol.

### Assumption 1: At-least-once event delivery for downstream consumers
Public/read-model consumers and downstream contexts may receive duplicate events.

**Domain consequence**
All downstream consequence handlers must be idempotent.

### Assumption 2: Client command retries are possible
Clients may retry commands due to timeouts or network uncertainty.

**Domain consequence**
Gameplay commands require stable action ids for idempotency.

### Assumption 3: Public projections may lag behind authoritative room state
Spectator and read-model views are not assumed to be perfectly synchronous.

**Domain consequence**
Clients must treat the authoritative room state as the source of truth; lagging public projections do not change gameplay outcomes.

### Assumption 4: Ordering is authoritative only within the room aggregate
External consumers should not assume globally ordered tournament-wide event arrival.

**Domain consequence**
Cross-context processors rely on source ids, round ids, and dedupe, not on perfect global ordering.

---

## 4. Open questions to validate later

### Gameplay and rules
1. Are jump-in and stacking mandatory rules or configurable variants?
2. Is hand count public to spectators, or should spectators only see names plus discard stack?
3. Is explicit player surrender allowed, or only automatic forfeit?
4. Are there per-turn timers beyond the disconnect skip behavior?
5. What exact card-point scoring system is used for tournament tie-breaks?

### Tournament behavior
6. Can byes occur when player counts do not divide evenly into rooms?
7. Must every non-final room always output exactly 3 advancing players, even after many forfeits?
8. Can rounds overlap operationally, or is the business policy strictly one active round at a time?
9. What is the exact tournament placement rating formula?

### Identity/security
10. Is spectator access anonymous, authenticated, or both?
11. Are players allowed to spectate their own completed matches?
12. What administrative powers exist for force-forfeit, force-end, or dispute correction?

### Recovery and disputes
13. Is there a formal business process for revoking a previously accepted room result after dispute review?
14. If public projection leaks hidden state due to a defect, what mandatory remediation process is required?

## 5. Recommended next validation priorities

If only a few open points can be clarified before the next deadline, these are the highest-value ones:

1. confirm optional vs mandatory advanced rules (stacking, jump-in)
2. confirm spectator public contract precisely
3. confirm how unresolved advancement ties are broken
4. confirm whether casual rooms are single-game only
5. confirm byes and underfilled room behavior in tournament rounds
