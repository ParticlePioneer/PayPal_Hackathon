# Domain workstream ? member A

Implement negotiation, inventory, reservations, quote lifecycle, the domain router, and the server-side quote adapter here. The API and adapter contracts are in `implementation_plan.md`. Keep domain migrations in `migrations/`; coordinate integration with member B.

Implemented contract documentation: [CONTRACTS.md](CONTRACTS.md).
Model configuration and smoke command: [MODEL_SMOKE.md](MODEL_SMOKE.md).
The authorized offline A2 runner and its limitations: [NEGOTIATION.md](NEGOTIATION.md).
The real-model gate remains pending; no stock reservation, quote, API, or payment
integration is provided by the terminal runner.

A3 persistence and the server-side quote adapter are available separately:
[PERSISTENCE.md](PERSISTENCE.md). This includes PostgreSQL migration, atomic
reservations, ownership, durable authorization claims, and expiry recovery.
The terminal runner is still read-only; router integration belongs to A4.

A4 router, trusted-session requirements, public request/response examples,
and synthetic PostgreSQL terminal checks: [API.md](API.md).
