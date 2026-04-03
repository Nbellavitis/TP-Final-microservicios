# 04 — Commands and Domain Events Catalog

## Catalog conventions

For each command below:
- **Decision owner** identifies the bounded context or aggregate that decides it.
- **Expected result** lists typical resulting events.
- **Idempotency notes** explain deduplication expectations.

Not every command always succeeds. Rejections may emit business-significant rejection events or may return a validation error without durable event emission, depending on policy. For important conflict/security cases, this design records explicit rejection events for auditing.

---

## A. Room Gameplay commands and events

### 1. CreateRoom
**Decision owner**: Room Gameplay / RoomSession  
**Purpose**: Create a casual room or a tournament-assigned room.

**Expected events**
- `RoomCreated`
- `RoomTypeAssigned`

**Idempotency**
- Idempotent by `commandId` or `roomId`

---

### 2. SeatPlayerInRoom
**Decision owner**: RoomSession  
**Expected events**
- `PlayerSeated`
- `RoomRosterUpdated`

**Rejected if**
- room already started
- seat already occupied
- player already seated elsewhere in same room

**Idempotency**
- duplicate seat request for same player/seat returns prior result

---

### 3. LockRoomRoster
**Decision owner**: RoomSession  
**Expected events**
- `RoomRosterLocked`

**Purpose**
Freeze roster before match initialization.

---

### 4. StartMatchInRoom
**Decision owner**: RoomSession  
**Expected events**
- `MatchStarted`
- `GameInitialized`
- `InitialHandsDealt`
- `FirstTurnSelected`
- `TurnBegan`

**Causality**
After roster lock and once starting conditions are met.

**Idempotency**
- duplicate start against same room/match profile must not create a second match

---

### 5. PlayCard
**Decision owner**: RoomSession  
**Required inputs**
- `playerId`
- `sessionId`
- `expectedSequence`
- `actionId`
- card reference
- chosen color if required

**Expected success events**
- `CommandAccepted`
- `CardPlayed`
- `ColorChosen` (if wild)
- `TurnEffectApplied` (skip/reverse/draw effects)
- `UnoChallengeWindowOpened` (if player now has one card and Uno not already declared)
- `PlayerReachedOneCard`
- `GameCompleted` (if this play ends the game)
- `MatchScoreUpdated`
- `NextGamePrepared` or `MatchCompleted`
- `RoomCompleted` (if room terminal)

**Expected rejection events**
- `StaleCommandRejected`
- `SessionInvalidCommandRejected`
- `IllegalMoveRejected`
- `ReplayCommandIgnored`

**Idempotency**
- exactly once per `actionId` within the room aggregate
- duplicate identical action returns prior decision
- duplicate conflicting payload under same `actionId` emits fraud/audit rejection

---

### 6. DrawCard
**Decision owner**: RoomSession  
**Expected success events**
- `CommandAccepted`
- `CardDrawn`
- `TurnBeganForSamePlayer` or `TurnEnded`
- `TurnAdvanced`

**Rejection examples**
- `StaleCommandRejected`
- `IllegalMoveRejected`

---

### 7. PassTurn
**Decision owner**: RoomSession  
**Expected success events**
- `CommandAccepted`
- `TurnPassed`
- `TurnAdvanced`

**Only legal if**
- ruleset allows pass after draw or because of disconnect-skip policy

---

### 8. CallUno
**Decision owner**: RoomSession  
**Expected success events**
- `UnoDeclared`

**Rejected if**
- player is not eligible to declare
- declaration arrives after next turn began
- stale or replayed request

**Idempotency**
- duplicate `CallUno` during same open eligibility window is harmless

---

### 9. ChallengeUno
**Decision owner**: RoomSession  
**Expected success events**
- `UnoChallengeInitiated`
- `UnoChallengeResolved`
- `PenaltyApplied`
- `CardsPenaltyDrawn`
- `TurnStateReconciled`

**Resolution variants**
- `UnoChallengeSucceeded`
- `UnoChallengeFailed`

**Rejected if**
- no open challenge window
- challenger not eligible
- next turn already began
- target player not challengeable

---

### 10. MarkPlayerDisconnected
**Decision owner**: RoomSession  
**Usually triggered by**: session continuity policy or room heartbeat policy  
**Expected events**
- `PlayerDisconnected`
- `ReconnectWindowOpened`
- `TurnSkippedDueToDisconnect` (if the player's turn is active and policy applies)
- `TurnAdvanced`

---

### 11. ReconnectPlayer
**Decision owner**: RoomSession with Identity/Session validation  
**Expected events**
- `PlayerReconnected`
- `ReconnectWindowClosed`

**Rejected if**
- session invalid
- reconnect window expired
- player already forfeited or room completed

**Important domain effect**
If successful, the player resumes with the same hand and room identity.

---

### 12. ExpireReconnectWindow
**Decision owner**: RoomSession policy/timer  
**Expected events**
- `ReconnectWindowExpired`
- `PlayerMarkedInactive`
- `PlayerForfeited` (if expiry occurred during player's turn or policy otherwise requires)
- `PlayerEliminatedFromTournamentRoom` (for tournament rooms)
- `GameAbandoned` or `RoomCompleted` if the remaining room state becomes terminal

---

### 13. EndGameByPlacement
**Decision owner**: RoomSession  
**Expected events**
- `GameCompleted`
- `PlacementRecorded`
- `CardPointTotalsRecorded`
- `MatchScoreUpdated`

**Causality**
Usually follows the final winning move, but modeled separately to clarify outcome finalization.

---

### 14. AdvanceMatchSeries
**Decision owner**: RoomSession  
**Expected events**
- `NextGamePrepared`
- `GameInitialized`
- `InitialHandsDealt`
- `TurnBegan`
or
- `MatchCompleted`
- `RoomCompleted` (when no further room gameplay remains)

---

### 15. ForfeitPlayer
**Decision owner**: RoomSession  
**Expected events**
- `PlayerForfeited`
- `PlayerRemovedFromCasualRoom` or `PlayerEliminatedFromTournamentRoom`
- `TurnAdvanced` if applicable
- `GameCompleted` / `RoomCompleted` if state becomes terminal

**Causes**
- reconnect expiry during active turn
- administrative security action
- explicit player surrender if the domain allows it

---

## B. Tournament Orchestration commands and events

### 16. CreateTournament
**Expected events**
- `TournamentCreated`

### 17. OpenTournamentRegistration
**Expected events**
- `TournamentRegistrationOpened`

### 18. RegisterPlayerForTournament
**Expected events**
- `PlayerRegisteredForTournament`

**Rejected if**
- registration closed
- player already registered
- player session/account not eligible

### 19. CloseTournamentRegistration
**Expected events**
- `TournamentRegistrationClosed`

### 20. StartTournament
**Expected events**
- `TournamentStarted`
- `RoundCreated`
- `RoundSeedingStarted`
- `PlayersPartitionedIntoRooms`
- `TournamentRoomProvisionRequested`

### 21. RecordTournamentRoomReady
**Expected events**
- `TournamentRoomReady`

### 22. RecordTournamentRoomResult
**Decision owner**: TournamentRound  
**Purpose**  
Consume the authoritative outcome emitted by Room Gameplay.

**Expected events**
- `TournamentRoomResultRecorded`
- `RoomAdvancementEvaluated`
- `PlayersAdvanced`
- `PlayersEliminated`

**Idempotency**
- room result report id or source room completion event id

### 23. CloseRoundAndPrepareNext
**Expected events**
- `RoundCompleted`
- `RoundCreated`
- `RoundSeedingStarted`
- `FinalRoomRequired` if <= 10 players remain
- `FinalRoomCreated` if threshold reached
- `TournamentCompleted` when final room already resolved

### 24. CompleteTournament
**Expected events**
- `TournamentCompleted`
- `TournamentPlacementsFinalized`
- `TournamentPlacementRatingUpdateRequested`

---

## C. Ranking commands and events

### 25. ApplyCasualGameOutcomeToRatings
**Decision owner**: Ranking / RatingProfile  
**Expected events**
- `EloUpdateRequested`
- `EloUpdated`
- `RatingHistoryRecorded`

**Rejected / ignored if**
- outcome already processed
- source outcome is not casual
- source game is abandoned

### 26. ApplyTournamentPlacementOutcome
**Expected events**
- `TournamentPlacementRatingUpdated`
- `RatingHistoryRecorded`

---

## D. Identity & Session commands and events

### 27. LoginPlayer
**Expected events**
- `PlayerLoggedIn`
- `PreviousSessionInvalidated` (if one existed)
- `ActiveSessionIssued`

### 28. ValidateSessionForAction
**Expected events**
- usually no durable success event needed
- on important rejection:
  - `SessionRejected`
  - `SessionMismatchDetected`

### 29. LogoutPlayer
**Expected events**
- `SessionClosed`

### 30. InvalidateSessionForSecurityReason
**Expected events**
- `SessionInvalidated`
- `SecurityAuditRecorded`

---

## E. Spectator View commands and events

Spectator View is primarily event-driven and read-only. Commands here are query/subscription oriented rather than authoritative gameplay commands.

### 31. PublishPublicRoomSnapshot
**Expected events**
- `PublicRoomSnapshotPublished`

### 32. PublishBracketProjection
**Expected events**
- `BracketProjectionUpdated`

### 33. DenySpectatorPrivateStateAccess
**Expected events**
- `SpectatorPrivacyViolationPrevented`

---

## F. Canonical domain event catalog by topic

### Room lifecycle
- `RoomCreated`
- `RoomTypeAssigned`
- `PlayerSeated`
- `RoomRosterUpdated`
- `RoomRosterLocked`
- `RoomStarted`
- `RoomCompleted`

### Match lifecycle
- `MatchStarted`
- `GameInitialized`
- `InitialHandsDealt`
- `NextGamePrepared`
- `MatchScoreUpdated`
- `MatchCompleted`

### Turn and gameplay
- `TurnBegan`
- `TurnAdvanced`
- `CardPlayed`
- `ColorChosen`
- `CardDrawn`
- `TurnPassed`
- `TurnEffectApplied`
- `PlayerReachedOneCard`

### Uno call mechanics
- `UnoDeclared`
- `UnoChallengeWindowOpened`
- `UnoChallengeInitiated`
- `UnoChallengeSucceeded`
- `UnoChallengeFailed`
- `UnoChallengeResolved`
- `PenaltyApplied`
- `CardsPenaltyDrawn`
- `UnoChallengeWindowClosed`

### Disconnects and forfeits
- `PlayerDisconnected`
- `ReconnectWindowOpened`
- `TurnSkippedDueToDisconnect`
- `PlayerReconnected`
- `ReconnectWindowClosed`
- `ReconnectWindowExpired`
- `PlayerMarkedInactive`
- `PlayerForfeited`

### Outcomes
- `PlacementRecorded`
- `CardPointTotalsRecorded`
- `GameCompleted`
- `GameAbandoned`

### Tournament progression
- `TournamentCreated`
- `TournamentRegistrationOpened`
- `PlayerRegisteredForTournament`
- `TournamentRegistrationClosed`
- `TournamentStarted`
- `RoundCreated`
- `RoundSeedingStarted`
- `PlayersPartitionedIntoRooms`
- `TournamentRoomProvisionRequested`
- `TournamentRoomReady`
- `TournamentRoomResultRecorded`
- `RoomAdvancementEvaluated`
- `PlayersAdvanced`
- `PlayersEliminated`
- `RoundCompleted`
- `FinalRoomRequired`
- `FinalRoomCreated`
- `TournamentPlacementsFinalized`
- `TournamentCompleted`

### Ranking
- `EloUpdateRequested`
- `EloUpdated`
- `TournamentPlacementRatingUpdateRequested`
- `TournamentPlacementRatingUpdated`
- `RatingHistoryRecorded`

### Security and auditing
- `SessionInvalidated`
- `PreviousSessionInvalidated`
- `SessionRejected`
- `SessionMismatchDetected`
- `SecurityAuditRecorded`
- `ReplayCommandIgnored`
- `StaleCommandRejected`
- `IllegalMoveRejected`
- `RateLimitTriggered`
- `SpectatorPrivacyViolationPrevented`

## Causality notes

### Example: from winning move to rating update
`PlayCard`  
-> `CardPlayed`  
-> `GameCompleted`  
-> `PlacementRecorded`  
-> `RoomCompleted` (if casual single-game room)  
-> `EloUpdateRequested`  
-> `EloUpdated`

### Example: from tournament room completion to next round
`GameCompleted` (final game in room match)  
-> `MatchCompleted`  
-> `RoomCompleted`  
-> `TournamentRoomResultRecorded`  
-> `PlayersAdvanced` / `PlayersEliminated`  
-> `RoundCompleted`  
-> `RoundCreated`

## Idempotency strategy summary

Every externally triggered or cross-context-mutating command should include a durable idempotency key:

- gameplay commands: `actionId`
- tournament result reporting: `reportId` or source `roomCompletionEventId`
- ranking updates: `sourceGameOutcomeId`
- session changes: `loginAttemptId` or `sessionVersion`

Rule of thumb:
- **same idempotency key + same payload** -> return prior outcome
- **same idempotency key + different payload** -> reject and audit
