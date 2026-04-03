# UnoArena DDD Domain Design

This repository contains a domain-driven design submission for **UnoArena: Global Real-Time Uno Platform & Massive Tournaments**.

The design is intentionally centered on **behavior, invariants, domain events, and consistency rules**. It keeps low-level infrastructure, deployment, protocol internals, and cloud sizing out of scope, per the assignment.

## Scope summary

This submission covers:

- EventStorming-oriented domain discovery
- Ubiquitous language and glossary
- Bounded contexts and context map
- Aggregates, entities, and value objects
- Commands and domain events with causality and idempotency notes
- End-to-end domain event narratives
- Failure paths, abuse scenarios, and recovery strategies
- Open questions and explicit assumptions

## Document index

1. [01-domain-glossary.md](./unoarena-ddd/01-domain-glossary.md)
2. [02-bounded-contexts-and-context-map.md](./unoarena-ddd/02-bounded-contexts-and-context-map.md)
3. [03-aggregates-entities-value-objects.md](./unoarena-ddd/03-aggregates-entities-value-objects.md)
4. [04-commands-and-domain-events.md](./unoarena-ddd/04-commands-and-domain-events.md)
5. [05-domain-event-flows.md](./unoarena-ddd/05-domain-event-flows.md)
6. [06-edge-cases-and-failure-paths.md](./unoarena-ddd/06-edge-cases-and-failure-paths.md)
7. [07-consistency-and-recovery-strategy.md](./unoarena-ddd/07-consistency-and-recovery-strategy.md)
8. [08-open-questions-and-assumptions.md](./unoarena-ddd/08-open-questions-and-assumptions.md)
9. [09-eventstorming-outcome.md](./unoarena-ddd/09-eventstorming-outcome.md)

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

## Notes
- The design assumes an event-driven environment, but does **not** prescribe specific infrastructure internals beyond explicit business-level assumptions listed in document 08.
- SSE, REST, and event bus concerns are treated only to the extent that they affect **domain behavior** and **consistency expectations**.
