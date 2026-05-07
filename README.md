# UnoArena Design and Architecture Checkpoints

This repository contains the Domain Design Checkpoint and the Architecture Checkpoint for **UnoArena: Global Real-Time Uno Platform & Massive Tournaments**.

The design package is centered on **behavior, invariants, domain events, and consistency rules**. The architecture package translates that same model into deployable services, interfaces, integration contracts, persistence ownership, and capacity reasoning.

## Scope summary

The design checkpoint covers:

- EventStorming-oriented domain discovery
- Ubiquitous language and glossary
- Bounded contexts and context map
- Aggregates, entities, and value objects
- Commands and domain events with causality and idempotency notes
- End-to-end domain event narratives
- Failure paths, abuse scenarios, and recovery strategies
- Open questions and explicit assumptions

The architecture checkpoint covers:

- Service decomposition per bounded context
- REST and async messaging contracts traceable to the design commands/events
- REST + SSE client connection model
- Rate limiting and session invalidation paths
- Per-context persistence and immutable game log strategy
- Mandatory sequence diagrams and container/context views
- Capacity sketch for 1,000,000-player tournaments and 100,000+ first-round rooms

## Design document index

1. [01-domain-glossary.md](01-domain-glossary.md)
2. [02-bounded-contexts-and-context-map.md](02-bounded-contexts-and-context-map.md)
3. [03-aggregates-entities-value-objects.md](03-aggregates-entities-value-objects.md)
4. [04-commands-and-domain-events.md](04-commands-and-domain-events.md)
5. [05-domain-event-flows.md](05-domain-event-flows.md)
6. [06-edge-cases-and-failure-paths.md](06-edge-cases-and-failure-paths.md)
7. [07-consistency-and-recovery-strategy.md](07-consistency-and-recovery-strategy.md)
8. [08-open-questions-and-assumptions.md](08-open-questions-and-assumptions.md)
9. [09-eventstorming-outcome.md](09-eventstorming-outcome.md)

## Architecture document index

10. [10-architecture-overview.md](10-architecture-overview.md)
11. [11-bounded-context-architecture.md](11-bounded-context-architecture.md)
12. [12-communication-patterns.md](12-communication-patterns.md)
13. [13-persistence-layer.md](13-persistence-layer.md)
14. [14-capacity-nfr-observability.md](14-capacity-nfr-observability.md)

## Alignment changelog

- [CHANGELOG-design.md](CHANGELOG-design.md)

## Modeling stance

### Core distinction
- **Game**: one individual Uno game.
- **Match**: a series of up to three games played by the same room roster.
- **Round**: one elimination tier of a tournament.
- **Tournament**: the overall competition spanning multiple rounds until the final room.

### Primary consistency idea
A **room session** is modeled as the strongest immediate consistency boundary for gameplay. This is because turn order, challenge windows, disconnect windows, legal plays, penalties, match progression, and room completion are tightly coupled and must be decided atomically from the room's authoritative state.

### Deliverable mapping
- Deliverables 1 and 2: `01`, `02`
- Deliverable 3: `03`
- Deliverable 4: `04`
- Deliverable 5: `05`
- Deliverable 6: `06`
- Deliverable 7: `07`
- Deliverable 8: `08`
- EventStorming artifact requested by methodology: `09`

### Architecture deliverable mapping
- Section 6.1 - Architecture of every bounded context: `10`, `11`
- Section 6.2 - Latest design package and changelog: `01` through `09`, `CHANGELOG-design.md`
- Section 6.3 - Communication patterns: `12`
- Section 6.4 - Persistence layer per context: `13`
- Section 6.5 - Capacity sketch: `14`
- Strongly recommended NFR, threat model, observability, ADRs: `14`

## Notes
- The design checkpoint assumptions remain listed in document 08.
- The architecture checkpoint keeps the same bounded contexts and event language. Any architecture-only clarification is documented in `CHANGELOG-design.md`.
