# 06 — Edge Cases and Failure-Path Analysis

This document addresses the specific failure categories required by the assignment and defines expected domain behavior plus emitted events.

---

## 1. Concurrent conflicting actions

### Scenario A: Two players try to act at the same time
Example: player A legally has the turn, but player B submits a move at nearly the same instant.

**Expected behavior**
- Only the command matching the current active turn owner and room sequence may succeed.
- The other command is rejected as illegal or stale, depending on what changed first.

**Typical events**
- accepted path:
  - `CommandAccepted`
  - `CardPlayed` or other valid action events
- rejected path:
  - `IllegalMoveRejected` or `StaleCommandRejected`

**Reason**
Gameplay consistency requires a single serial action history per room.

---

### Scenario B: Two identical requests from the same player arrive twice
Example: network retry duplicates `PlayCard`.

**Expected behavior**
- If the same `actionId` and same payload arrive twice, the second is deduplicated.
- The room returns the original accepted/rejected outcome.
- No second state transition occurs.

**Events**
- first request:
  - normal acceptance or rejection events
- duplicate:
  - `ReplayCommandIgnored`

---

### Scenario C: Same idempotency key but different payload
Example: same `actionId`, but a different card is claimed.

**Expected behavior**
- reject as malformed or suspicious
- record a security or audit event

**Events**
- `ReplayCommandIgnored` or `SuspiciousReplayDetected`
- `SecurityAuditRecorded`

---

### Scenario D: Competing fast mechanics
Example: a player plays their second-to-last card, another player challenges Uno, while the next player's turn begins almost simultaneously.

**Expected behavior**
- the authoritative room sequence decides the ordering
- if `TurnBegan(nextPlayer)` is already committed, the challenge window is closed
- late challenge is rejected
- if challenge committed first while the window was still open, it resolves normally

**Events**
Possible outcomes:
- `UnoChallengeInitiated`
- `UnoChallengeResolved`
or
- `IllegalMoveRejected` because the challenge window is already closed

---

### Scenario E: Optional rules like jump-in or stacking create true contention
**Expected behavior**
- such rules must be explicitly part of the room ruleset
- if enabled, they still resolve through one authoritative serialized action stream
- no “simultaneous truth” is allowed

**Events**
- accepted interrupt:
  - `TurnInterruptedByRuleVariant`
  - subsequent legal action events
- rejected late interrupt:
  - `IllegalMoveRejected`

---

## 2. Disconnections and late rejoin attempts

### Scenario A: Player disconnects, reconnects within 60 seconds
**Expected behavior**
- room keeps their hand intact
- during the disconnect window, their turns are skipped; no bot substitution
- on reconnect, player resumes authority in the room

**Events**
- `PlayerDisconnected`
- `ReconnectWindowOpened`
- possibly `TurnSkippedDueToDisconnect`
- `PlayerReconnected`
- `ReconnectWindowClosed`

---

### Scenario B: Player disconnects and does not return
**Expected behavior**
- once reconnect window expires, the player becomes inactive
- if expiry occurs during their turn, they forfeit automatically
- casual room: room continues with remaining players if still viable
- tournament room: player is eliminated from the tournament match

**Events**
- `ReconnectWindowExpired`
- `PlayerMarkedInactive`
- `PlayerForfeited`
- `PlayerRemovedFromCasualRoom` or `PlayerEliminatedFromTournamentRoom`

---

### Scenario C: Player tries to rejoin after expiry
**Expected behavior**
- late rejoin is denied
- original hand is not restored into active play
- no gameplay state is changed

**Events**
- `LateRejoinRejected`
- optional `SecurityAuditRecorded` if abuse is suspected

---

### Scenario D: Player reconnects with a newer valid session because old one was invalidated
**Expected behavior**
- allowed only if:
  1. the new session is now the active session for the player, and
  2. the room reconnect window is still open
- gameplay continuity is restored under the new active session identity.
- *Note on trust mechanisms:* The API gateway or Identity Context validates the new session token and injects the stable canonical `PlayerId` into the command payload. Room Gameplay checks the seated `PlayerId` rather than the `SessionId` to resume the game, while continuing to obey the new `expectedSequence`.

**Events**
- `PreviousSessionInvalidated`
- `PlayerReconnected`

---

### Scenario E: All opponents forfeit during an active game (Last Man Standing)
**Expected behavior**
- the single remaining player is immediately placed 1st by default.
- the game completes automatically since no valid competitive state remains.
- casual room: match outcome is resolved.
- tournament room: final match outcomes evaluate immediately, guaranteeing the remaining player advances.

**Events**
- `PlayerForfeited` (for the final disconnecting opponent)
- `GameCompleted` (with last man standing declared winner)
- `MatchCompleted` / `RoomCompleted`

---

## 3. Stale commands and replayed commands

### Scenario A: Client acts on old room state
**Expected behavior**
- command is rejected with no state change
- caller must reconcile using the latest authoritative state

**Events**
- `StaleCommandRejected`

**Notes**
This is one of the most important reactive consistency contracts in the domain.

---

### Scenario B: Old `CallUno` arrives after the next turn began
**Expected behavior**
- reject, because declaration window already closed
- do not retroactively reopen the challenge logic

**Events**
- `IllegalMoveRejected` or `StaleCommandRejected`

---

### Scenario C: Replayed tournament result report
**Expected behavior**
- consume once
- ignore duplicates by source completion id

**Events**
- `DuplicateRoomResultIgnored` or equivalent audit record

---

## 4. Partial failures between contexts

### Scenario A: Room completed, tournament result consumer temporarily down
**Expected behavior**
- room remains completed
- tournament progression waits until the authoritative result is consumed
- duplicate delivery is safe via idempotent report consumption

**Events**
- original:
  - `RoomCompleted`
- later upon successful consumption:
  - `TournamentRoomResultRecorded`
  - `PlayersAdvanced`
  - `PlayersEliminated`

**Business stance**
Do not reopen the room. The room outcome is final.

---

### Scenario B: Room completed, ranking update fails
**Expected behavior**
- gameplay result remains valid
- ranking retries later
- duplicate application prevented by outcome id dedupe

**Events**
- `EloUpdateRequested`
- delayed `EloUpdated`
- possible `RatingUpdateRetryScheduled` as internal policy signal

---

### Scenario C: Tournament round almost complete, one room result is missing
**Expected behavior**
- round does not close prematurely
- orchestration remains in a waiting state
- manual or automated reconciliation may be required if the missing result breaches operational thresholds

**Events**
- `RoundAwaitingOutstandingRoomResults`
- later `RoundCompleted` only after resolution

---

### Scenario D: Spectator projection lags or drops updates
**Expected behavior**
- authoritative gameplay is unaffected
- spectator can recover from snapshot plus subsequent public events
- no private information may be exposed during recovery

**Events**
- `PublicRoomSnapshotPublished`

---

## 5. Security and abuse scenarios

### Scenario A: Session takeover or dual-session play attempt
**Expected behavior**
- new login invalidates old session
- old session commands are rejected immediately
- room continuity depends on reconnect rules under the new active session

**Events**
- `PreviousSessionInvalidated`
- `SessionRejected`
- `SecurityAuditRecorded`

---

### Scenario B: Action spam or flooding
Examples:
- repeated move attempts when not the player's turn
- brute-force room actions
- abusive tournament registration attempts

**Expected behavior**
- rate limit policy throttles or rejects abusive command volume
- rejected actions do not mutate gameplay or tournament state
- persistent abuse is audited

**Events**
- `RateLimitTriggered`
- `SecurityAuditRecorded`

---

### Scenario C: Forged or tampered cross-context result message
**Expected behavior**
- tournament/ranking consumers reject unverifiable or malformed result reports
- no advancement or rating mutation occurs
- investigation trail is preserved

**Events**
- `UntrustedRoomResultRejected`
- `SecurityAuditRecorded`

---

### Scenario D: Player attempts unauthorized action for another seat
**Expected behavior**
- reject because session-player identity does not match the seated player
- audit if malicious

**Events**
- `SessionMismatchDetected`
- `SecurityAuditRecorded`

---

## 6. Spectator privacy violations

### Scenario A: Spectator attempts to query another player's hand
**Expected behavior**
- deny the request
- do not leak whether a hidden card exists beyond approved public information
- audit suspicious access pattern if necessary

**Events**
- `SpectatorPrivacyViolationPrevented`

---

### Scenario B: Player tries to use spectator channel as an information side-channel
Example: same human uses a player client plus a spectator client to seek hidden data.

**Expected behavior**
- spectator projection still exposes only public data
- there is no additional hidden room state to retrieve
- repeated suspicious probing may be audited

**Events**
- `SpectatorPrivacyViolationPrevented`
- `SecurityAuditRecorded` if attack heuristics trigger

---

### Scenario C: Public event accidentally contains private hand content
**Expected behavior**
- this is a severe domain contract violation
- downstream consumer must reject the malformed public event schema
- incident is audited and quarantined

**Events**
- `PublicProjectionSchemaViolationDetected`
- `SecurityAuditRecorded`

---

## 7. Tournament-specific edge cases

### Scenario A: Tie for advancement after best-of-three
**Expected behavior**
Apply tie-breakers in this exact order:
1. higher match wins
2. lower cumulative card-point total in tied games
3. earliest time of final-game completion

If still tied after the defined rules, the domain currently lacks a validated fourth tie-breaker and must flag manual/business resolution or an additional approved policy.

**Events**
- `RoomAdvancementEvaluated`
- `PlayersAdvanced`
- `TieBreakApplied`
- possibly `ManualResolutionRequired` if unresolved after specified rules

---

### Scenario B: Too few players remain in a tournament room due to forfeits
**Expected behavior**
- room match resolves according to remaining valid competitors and room rules
- Tournament Orchestration still consumes the authoritative room result
- advancement count may effectively be less than 3 if insufficient active competitors remain

**Events**
- `PlayerForfeited`
- `MatchCompleted`
- `RoomCompleted`

---

### Scenario C: Final room created with 10 or fewer players
**Expected behavior**
- tournament stops creating normal elimination rounds
- one final room resolves the tournament

**Events**
- `FinalRoomRequired`
- `FinalRoomCreated`
- later `TournamentCompleted`

---

## 8. Abuse-resistant expected behavior summary

Across all failure paths:
- stale or replayed commands do not mutate authoritative state
- duplicate downstream messages are safe
- public projections do not contain hidden state
- room completion is final once emitted
- downstream failures delay side effects, not core outcome truth
