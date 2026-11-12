# AgentNegotiate

The project described in [implementation_plan.md](implementation_plan.md): OpenRouter buyer/seller negotiation, a stock-backed quote, and PayPal Sandbox authorization. B4 integration is implemented; the deployed end-to-end acceptance gate remains to be verified. Inventory and fulfillment are simulated.

## Ownership

| Member | Area |
| --- | --- |
| A | `backend/domain/`, negotiation API, inventory, and domain migrations |
| B | `backend/payments/`, app entry point, payment migrations, `frontend/src/CheckoutButton.tsx`, deployment, and integration |
| C | Remaining frontend, buyer journey, fixtures, and frontend state |
| D | `qa/`, acceptance, README, and submission materials |

Work on short-lived branches. Use the interface and fixture examples in the implementation plan as the source of truth. Coordinate changes to shared interfaces with their consumers.

## Local setup

Copy `.env.example` to `.env` and fill in local values as needed. Never commit credentials. A PayPal client ID can be exposed to the browser; the client secret, session secret, and model key must remain server-side.

Backend (Python 3.10+):

```sh
python -m venv .venv
# Activate .venv using your shell, then:
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --env-file .env --reload
```

Check `http://127.0.0.1:8000/health`. It checks the process only. The command above explicitly loads `.env`; integrated routes require `B4_ENABLED=true`, PostgreSQL migrations, and the settings in the [B4 deployment guide](backend/payments/B4_DEPLOYMENT.md). The default disabled flags allow the health endpoint to start without provider calls.

Frontend (Node.js 20.19+ or 22.12+):

```sh
cd frontend
npm install
npm run dev
```

On Windows PowerShell, use `npm.cmd` in place of `npm` if the execution policy blocks `npm.ps1`.

The frontend supports labeled fixtures without provider credentials and a live API mode. Run `npm run build` to verify the production build. For integrated checkout, build with `VITE_DEFAULT_MODE=api` and the public `VITE_PAYPAL_CLIENT_ID`, then use the frontend served by FastAPI at `/`.

## Integration notes

The app uses one FastAPI service and PostgreSQL database. Startup migrations, when explicitly enabled, apply domain migrations before payment migrations. Live negotiation uses OpenRouter; checkout uses the server-owned quote amount and PayPal Sandbox. See [B4 deployment and acceptance](backend/payments/B4_DEPLOYMENT.md), [payments setup](backend/payments/README.md), and [QA](qa/README.md).
