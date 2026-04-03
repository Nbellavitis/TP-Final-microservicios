# 09 — EventStorming Outcome

This document summarizes the EventStorming-style discovery outcome requested by the assignment. It is organized around:
- domain events
- commands
- policies
- aggregates
- invariants
- exceptional flows
- cross-context interactions

## 1. EventStorming legend used in this document

- **Command**: something an actor or policy asks the domain to do
- **Domain Event**: something meaningful that happened in the domain
- **Policy**: a business reaction that turns one event into a later command
- **Aggregate**: the consistency boundary deciding commands
- **Read Model**: downstream projection or public view

---

## 2. Main business flow — room lifecycle

### Flow board (textual)
1. **Command**: `CreateRoom`
2. **Event**: `RoomCreated`
3. **Command**: `SeatPlayerInRoom`
4. **Event**: `PlayerSeated`
5. **Command**: `LockRoomRoster`
6. **Event**: `RoomRosterLocked`
7. **Command**: `StartMatchInRoom`
8. **Event**: `MatchStarted`
9. **Event**: `GameInitialized`
10. **Event**: `InitialHandsDealt`
11. **Event**: `TurnBegan`
12. **Command**: `PlayCard` / `DrawCard` / `PassTurn` / `CallUno` / `ChallengeUno`
13. **Events**: gameplay effects, challenge outcomes, penalties, turn advancement
14. **Event**: `GameCompleted`
15. **Policy**: if match unresolved -> `AdvanceMatchSeries`
16. **Event**: `NextGamePrepared` / `MatchCompleted`
17. **Event**: `RoomCompleted`

### Aggregate
- `RoomSession`

### Invariants protected
- one active turn
- one authoritative room version
- one authoritative room completion
- timely Uno challenge closure
- reconnect preserves hand

---

## 3. Main business flow — match lifecycle inside a tournament room

### Flow board
1. **Event**: `MatchStarted`
2. **Event**: `GameInitialized (game 1)`
3. **Event**: `GameCompleted (game 1)`
4. **Event**: `MatchScoreUpdated`
5. **Policy**: if series unresolved -> `AdvanceMatchSeries`
6. **Event**: `GameInitialized (game 2)`
7. **Event**: `GameCompleted (game 2)`
8. **Event**: `MatchScoreUpdated`
9. **Policy**: if series unresolved and needed -> `AdvanceMatchSeries`
10. **Event**: `GameInitialized (game 3)`
11. **Event**: `GameCompleted (game 3)`
12. **Event**: `CardPointTotalsRecorded`
13. **Event**: `MatchCompleted`
14. **Event**: `RoomCompleted`

### Important policy decision
At `MatchCompleted`, the room must emit enough facts for tournament tie-breaks:
- match wins
- cumulative card-point total
- final-game completion timing

---

## 4. Main business flow — tournament progression

### Flow board
1. **Command**: `CreateTournament`
2. **Event**: `TournamentCreated`
3. **Command**: `RegisterPlayerForTournament`
4. **Event**: `PlayerRegisteredForTournament`
5. **Command**: `StartTournament`
6. **Event**: `TournamentStarted`
7. **Event**: `RoundCreated`
8. **Event**: `PlayersPartitionedIntoRooms`
9. **Policy**: for each room assignment -> `CreateRoom` in Room Gameplay
10. **Event**: `TournamentRoomReady`
11. **Event**: `RoomCompleted`
12. **Command**: `RecordTournamentRoomResult`
13. **Event**: `TournamentRoomResultRecorded`
14. **Policy**: evaluate advancement
15. **Events**: `PlayersAdvanced`, `PlayersEliminated`
16. **Policy**: if all rooms resolved and remaining > 10 -> `CloseRoundAndPrepareNext`
17. **Events**: `RoundCompleted`, `RoundCreated`
18. **Policy**: if remaining <= 10 -> `FinalRoomCreated`
19. **Event**: final room `RoomCompleted`
20. **Event**: `TournamentCompleted`

### Aggregates
- `Tournament`
- `TournamentRound`

### Invariants protected
- player assigned to one room per round
- one advancement decision per player per round
- no tournament completion before final room result

---

## 5. Exceptional flow — stale gameplay commands

### Flow board
1. **Command**: `PlayCard(expectedSequence = old)`
2. Aggregate compares to current room version
3. **Event**: `StaleCommandRejected`

### Policy outcome
Client must reconcile using current authoritative room state.

### Invariant protected
No stale command mutates room state.

---

## 6. Exceptional flow — disconnect and reconnect

### Flow board
1. **Event**: `PlayerDisconnected`
2. **Policy**: open reconnect window
3. **Event**: `ReconnectWindowOpened`
4. If player's turn occurs while disconnected:
   - **Event**: `TurnSkippedDueToDisconnect`
5. If reconnect before expiry:
   - **Command**: `ReconnectPlayer`
   - **Event**: `PlayerReconnected`
6. If expiry during player's turn:
   - **Command**: `ExpireReconnectWindow`
   - **Event**: `PlayerForfeited`

### Invariants protected
- no bot substitution
- reconnect restores original hand
- post-expiry late join does not restore authority

---

## 7. Exceptional flow — Uno challenge timing

### Flow board
1. **Event**: `CardPlayed`
2. If acting player now has one card:
   - **Event**: `PlayerReachedOneCard`
   - **Event**: `UnoChallengeWindowOpened`
3. Optional command: `CallUno`
   - **Event**: `UnoDeclared`
4. Opponent may send `ChallengeUno`
5. Aggregate checks if:
   - window still open
   - next turn not begun
   - challenger eligible
6. **Event**: `UnoChallengeResolved`
7. Outcome:
   - target failed to call -> `PenaltyApplied` to target
   - target did call -> `PenaltyApplied` to challenger

### Invariants protected
- challenge is only legal during the window
- once next turn begins, the window is closed

---

## 8. Cross-context interactions discovered by EventStorming

### Room Gameplay -> Tournament Orchestration
**Triggering event**: `RoomCompleted` for tournament room  
**Business effect**: record results, advance top 3, eliminate others

### Room Gameplay -> Ranking
**Triggering event**: `GameCompleted` in casual room  
**Business effect**: apply Elo unless abandoned

### Identity & Session -> Room Gameplay
**Triggering event**: `PreviousSessionInvalidated` or session validation outcome  
**Business effect**: reject old-session commands

### Room Gameplay / Tournament Orchestration -> Spectator View
**Triggering events**: public room and tournament events  
**Business effect**: update public projections without hidden state

### All sensitive contexts -> Audit
**Triggering events**: penalties, shuffles, disconnect forfeits, rating changes, invalid sessions  
**Business effect**: immutable dispute trail

---

## 9. Policy decisions identified

### Policies inside Room Gameplay
- open Uno challenge window after reaching one card
- close challenge window when next turn begins
- skip disconnected player's turn during reconnect window
- forfeit when reconnect window expires during active turn
- start next game if match not yet resolved
- complete room when no further gameplay remains

### Policies inside Tournament Orchestration
- create next round when current round fully resolved and remaining players > 10
- create final room when remaining players <= 10
- apply advancement tie-breaks from authoritative room result

### Policies inside Ranking
- ignore abandoned casual game outcomes
- dedupe repeated game outcome processing

---

## 10. High-value invariants discovered

### Gameplay invariants
- exactly one active turn
- exactly one accepted action per room version transition
- no late Uno challenge after next turn starts
- reconnect within window preserves original hand
- completed room cannot accept new gameplay actions

### Tournament invariants
- one player in one room per round
- one room result counted once
- one final room only when threshold reached
- no player both advanced and eliminated in same round

### Security/privacy invariants
- one active session per player
- spectator view never includes private hands
- malformed or untrusted cross-context inputs are rejected

---

## 11. Read models discovered

- public room spectator view
- public tournament bracket view
- player rating leaderboard
- player statistics view
- audit/dispute history view

These are all downstream consumers of authoritative events, not sources of truth.

## 12. EventStorming conclusion

The EventStorming exercise reveals that **Room Gameplay** is the highest-intensity decision core, because nearly every hard rule in the prompt converges there:
- split-second actions
- strict sequencing
- Uno challenge timing
- disconnect and forfeit behavior
- series progression
- room completion

Meanwhile, **Tournament Orchestration** is a coordination domain that must trust, consume, and react to authoritative room outcomes, and **Ranking/Spectator/Audit** are downstream consequence or projection domains.

That separation keeps the model behaviorally complete without collapsing everything into one oversized context.
