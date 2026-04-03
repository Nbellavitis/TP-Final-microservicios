# 01 — Domain Glossary

## Ubiquitous language

### Core competition terms

**Player**  
A registered participant who can join casual rooms, enter tournaments, play games, spectate allowed rooms, and hold ratings.

**Room**  
A bounded play space containing a fixed roster for a gameplay session. A room moves through `waiting`, `in_progress`, and `completed`. A room is either **casual** or **tournament-bound**.

**Seat**  
A player's position inside a room. A seat determines turn order and is stable for the room session.

**Spectator**  
A non-playing observer attached to a room's public view. A spectator can consume public room state but cannot access hidden information such as private hands.

**Game**  
A single Uno game, from initial dealing to final placement in that game.

**Match**  
A bounded series of up to **three games** played by the same room roster. Tournament rooms always run a match. <mark>Casual rooms may be modeled as a match profile with `maxGames = 1`.</mark>

**Round**  
A single elimination tier of a tournament. A round partitions eligible players into rooms and produces a reduced set of advancing players.

**Tournament**  
The full competition lifecycle, from registration through final room completion.

**Final Room**  
The last tournament room created once the tournament has 10 or fewer remaining players. It resolves the tournament's final placements.

### Gameplay terms

**Turn**  
The exclusive opportunity for a single seat to act in a game. A turn begins when the game designates an active player and ends when a legal turn-ending action, timeout policy, or skip effect advances control.

**Action**  
A player-intended operation against room gameplay state, such as play card, draw card, call Uno, challenge Uno, or pass when pass is legal.

**Sequence Number**  
A client-supplied expected state token representing the room's current authoritative version. It prevents stale or reordered commands from mutating room state.

**Legal Move**  
An action accepted by the game rules and the room's current authoritative state.

**Stale Command**  
A command targeting an older room version than the current one. It is rejected and produces no gameplay state transition.

**Replay Command**  
A repeated command with the same idempotency key or action identifier. It returns the prior outcome and does not execute twice.

**Challenge Window**  
The 5-second interval during which an opponent may challenge whether the acting player correctly called “Uno!” after reaching one remaining card. It closes earlier if the next player begins their turn.

**Uno Declaration**  
The acting player's explicit “Uno!” call after playing their second-to-last card and before the next player's turn begins.

**Penalty Draw**  
A forced card draw imposed by rules, such as losing an Uno challenge.

**Jump-In**  
A same-card interruption rule, if supported in the ruleset. Because it creates cross-turn contention, it must be modeled as an explicitly enabled ruleset option, not assumed universally.

**Stacking**  
A rule variant that allows chaining certain penalty cards. Because it materially changes legality and timing, it is also modeled as a ruleset option.

**Chosen Color**  
The color declared after playing a wild card. It becomes part of the authoritative game state.

**Discard Stack**  
The ordered sequence of publicly played cards. It is visible to players and spectators.

**Draw Pile**  
The hidden remaining deck from which cards are drawn.

**Card-Point Total**  
The cumulative point total of unplayed cards used as a tournament tie-breaker when players tie on match wins.

### Lifecycle and tournament terms

**Room Session**  
The complete authoritative gameplay state for one room, including membership, seat order, current match, active game, timers, penalties, and completion outcome.

**Room Completion**  
The point at which a room has produced its terminal outcome. In casual play, this yields final placement and possible Elo update. In tournament play, it yields advancement results and elimination results.

**Advancement**  
The act of qualifying from a tournament room into the next round.

**Elimination**  
The act of being removed from further tournament contention.

**Round Seeding**  
The process of assigning eligible players to rooms for a round.

**Placement**  
The final ordering of players in a completed game, room, match, or tournament, depending on context.

**Tournament Placement Rating**  
A rating distinct from casual Elo, updated based on tournament outcome rather than casual room results.

### Identity, security, and continuity terms

**Identity**  
The verified player account and its permissions.

**Session**  
The currently active authenticated login instance for a player.

**Single-Active-Session Rule**  
A business rule stating that logging in from a new session invalidates the old session.

**Disconnect Window**  
A 60-second grace interval after a player disconnects. During it, the player may reconnect and resume with the same hand.

**Inactive Player**  
A disconnected player whose grace window has not yet expired. Their turns are skipped; a bot is never substituted.

**Forfeit**  
A terminal loss triggered by policy. In casual rooms, the player leaves the game and the room continues if possible. In tournament rooms, the player loses the match and is eliminated.

**Late Rejoin**  
A reconnect attempt after the disconnect window expired or after session invalidation. It does not restore gameplay authority.

**Audit Log**  
An immutable record of sensitive domain decisions, including session invalidation, authoritative random outcomes, disputes, and penalties.

### Ratings and analytics terms

**Casual Elo**  
The global Elo-like rating updated only from completed casual games.

**Elo Delta**  
The change applied to a player's casual rating after a completed casual game, computed from final placement.

**Abandoned Game**  
A game that ends without a valid competitive outcome, such as all remaining players forfeiting. It produces no Elo change.

**Bracket View**  
A read-optimized representation of tournament structure and progression.

**Player Stats View**  
A read-optimized projection of player performance, separate from the gameplay authority.

## Key terminology distinctions required by the assignment

### Game vs. Match vs. Round vs. Tournament

- **Game**: one self-contained Uno game.
- **Match**: the series played by one room roster, up to 3 games in tournament play.
- **Round**: the stage of a tournament where all currently eligible players are partitioned into rooms and compete for advancement.
- **Tournament**: the entire elimination competition across all rounds.

## Vocabulary constraints

To keep the model precise:

- Use **room** for the authoritative gameplay boundary, not “table” or “lobby.”
- Use **match** only for the best-of-three series, not as a synonym for room.
- Use **game** only for one individual Uno game.
- Use **round** only for one elimination tier of a tournament.
- Use **spectator view** for the public projection, not for the room aggregate itself.
- Use **placement rating** for tournaments and **Elo** for casual play; never mix them.
