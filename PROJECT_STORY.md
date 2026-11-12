**Inspiration**

Online shopping makes it easy to find products, but finding an offer that fits a specific budget, quantity, and delivery deadline still requires manual conversations. For a bulk purchase, the cheapest option may arrive too late, while a slightly different combination could meet every requirement.

We built **AgentNegotiate** to explore a simple question: what if AI agents could work through those tradeoffs for buyers and sellers, then connect an agreed deal to PayPal?

**What it does**

AgentNegotiate gives buyers and sellers separate AI agents that negotiate within their respective constraints. Buyers specify quantity, budget, acceptable colors, and delivery requirements. The agents exchange proposals, while the backend checks whether those proposals satisfy business rules and available inventory.

For example, a buyer ordering 30 shirts might need 12 by Friday and the remainder by Monday. Instead of accepting a cheaper offer that misses the deadline, the agents can negotiate a split delivery.

A valid agreement becomes a stock-backed, time-limited quote that the buyer can approve through **PayPal Sandbox**. When the requirements cannot be met, the application explains why no deal is available.

**How we built it**

We built the interface with **React, TypeScript, and Vite**, backed by **FastAPI and PostgreSQL**. Our live negotiation agents use **OpenRouter**, with structured actions validated through **Pydantic**.

We separated negotiation, inventory, and payment responsibilities. AI agents propose terms; server-side logic validates them, reserves stock, and determines the checkout amount. PayPal handles buyer approval and sandbox payment authorization.

The prototype uses real model calls and PayPal Sandbox requests, with simulated inventory and fulfillment.

**Challenges we faced**

Making AI responses dependable was one of our biggest challenges. During development, we tested different model configurations and encountered timeouts, incomplete outputs, and invalid proposals. We also learned that an HTTP 200 response does not necessarily mean a usable negotiation action was returned.

We addressed these issues with bounded turns, configurable output limits, strict response validation, and conversation records that made failures easier to investigate.

Connecting negotiation to checkout introduced another challenge: an agreement must remain consistent when users refresh, retry, or compete for the same stock. That required persistent state, atomic reservations, quote expiry, and safeguards against duplicate payment operations.

**What we learned**

Building agentic commerce takes more than connecting a model to a payment button. Flexible negotiation needs deterministic checks around money, inventory, privacy, and authorization.

Our most valuable lesson was that a trustworthy system must handle an unsuccessful negotiation as carefully as a successful one. AgentNegotiate brings that principle into a visible, buyer-controlled journey from requirements to agreement to PayPal checkout.
