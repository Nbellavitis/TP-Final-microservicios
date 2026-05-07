# CHANGELOG-design.md

This changelog satisfies Architecture Checkpoint deliverable 6.2. It records whether the approved Design Checkpoint artifacts were changed to align with the architecture.

## Summary

No domain design artifact from `01-domain-glossary.md` through `09-eventstorming-outcome.md` was changed for this Architecture Checkpoint. The architecture preserves the same bounded contexts, aggregate boundaries, command names, domain event names, and non-negotiable domain guarantees from the 10/10 Design Checkpoint.

`README.md` was updated only as an index so reviewers can navigate both the existing design package and the new architecture package. This is not a domain model change.

## Artifact-by-artifact status

| Design Checkpoint deliverable | Artifact | Change status | Reason / architecture constraint | Guarantee preserved |
|---|---|---|---|---|
| Deliverable 1 - Domain glossary | `01-domain-glossary.md` | No change | Architecture uses the same meanings for game, match, round, tournament, casual Elo, tournament placement rating, disconnect window, and challenge window | Terminology remains consistent; match vs game is not weakened |
| Deliverable 2 - Bounded contexts and context map | `02-bounded-contexts-and-context-map.md` | No change | Architecture maps each approved context to deployable containers; RNG/Deck is an internal Room Gameplay service, not a new bounded context | Context boundaries remain intact; Spectator View remains first-class |
| Deliverable 3 - Aggregates, entities, value objects | `03-aggregates-entities-value-objects.md` | No change | Runtime ownership follows the approved aggregates: `RoomSession`, `Tournament`, `TournamentRound`, `PlayerSession`, `RatingProfile` | Strong room sequencing, match state, tournament advancement, session, and rating invariants remain intact |
| Deliverable 4 - Commands and domain events catalog | `04-commands-and-domain-events.md` | No change | REST APIs and async topics trace to the existing command/event names. Internal timer commands produce existing documented events such as `UnoChallengeWindowClosed` and `ReconnectWindowExpired` | No command/event rename, split, or merge was introduced |
| Deliverable 5 - Domain event flow narratives | `05-domain-event-flows.md` | No change | Architecture sequence diagrams implement the same room completion, tournament advancement, and ranking flows | Room results remain authoritative; downstream failures do not reopen rooms |
| Deliverable 6 - Edge cases and failure paths | `06-edge-cases-and-failure-paths.md` | No change | Architecture assigns runtime homes to stale commands, disconnects, replay, partial failures, abuse, and spectator privacy cases | Stale/replayed commands, late reconnects, security abuse, and privacy violations remain explicitly handled |
| Deliverable 7 - Consistency and recovery strategy | `07-consistency-and-recovery-strategy.md` | No change | Architecture provides concrete mechanisms for the same business recovery strategy: outbox, idempotent consumers, durable timers, DLQs, and projections | No eventual consistency was moved into turn legality or challenge timing |
| Deliverable 8 - Open questions and assumptions | `08-open-questions-and-assumptions.md` | No change | Architecture keeps the same assumptions, especially REST+SSE, at-least-once downstream delivery, command retries, and projection lag | Elo scope, tournament advancement, and spectator privacy assumptions are unchanged |
| EventStorming artifact | `09-eventstorming-outcome.md` | No change | Architecture references the same EventStorming flows and policies | Event causality remains traceable from command to event to policy |

## Architecture-only clarifications

The following points were added in architecture documents but do not change the domain model:

- `10-architecture-overview.md` assigns runtime owners for sequence enforcement, log-before-broadcast, timers, single-active-session stream termination, spectator projection privacy, match series coordination, and abandoned/completed outcome separation.
- `11-bounded-context-architecture.md` maps each bounded context to services, APIs, topics, and owned storage boundaries.
- `12-communication-patterns.md` defines REST+SSE connection handling, rate limiting layers, and integration failure semantics.
- `13-persistence-layer.md` defines per-context persistence choices and immutable game log access controls.
- `14-capacity-nfr-observability.md` adds the mandatory capacity sketch and supporting NFR, threat, observability, and ADR material.

## Explicit guarantee affirmation

No Design Checkpoint guarantee was weakened or dropped:

- Casual Elo is still updated only for non-abandoned casual games.
- Tournament play still uses tournament placement rating, not casual Elo.
- Tournament rooms still play best-of-three matches.
- Top 3 advancement, card-point tie-break, and final-game completion-time tie-break remain owned by Tournament Orchestration.
- `RoomSession` still owns turn legality, sequence checks, Uno challenge timing, reconnect windows, forfeits, match progression, and room completion.
- Spectators still never receive private hands or hidden draw pile state.
- Single-active-session is strengthened at runtime by the architecture because invalidation now reaches live SSE gateways.
