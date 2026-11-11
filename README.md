# AgentNegotiate

A team scaffold for the project described in [implementation_plan.md](implementation_plan.md). The intended flow is AI-assisted negotiation, a stock-backed quote, and PayPal Sandbox authorization. The scaffold does not implement that flow yet.

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
python -m uvicorn backend.main:app --reload
```

Check `http://127.0.0.1:8000/health`. The scaffold does not load `.env` or connect to a database yet; the relevant owners will add configuration and migrations.

Frontend (Node.js 20.19+ or 22.12+):

```sh
cd frontend
npm install
npm run dev
```

On Windows PowerShell, use `npm.cmd` in place of `npm` if the execution policy blocks `npm.ps1`.

The frontend is a placeholder and works without provider credentials. Run `npm run build` to verify the production build. The lockfile should be committed once dependencies are installed.

## Integration notes

The plan specifies one FastAPI service and PostgreSQL database. Apply domain migrations before payment migrations when those are implemented. The frontend checkout slot currently displays a disabled placeholder; no real PayPal or AI calls are made. See [QA](qa/README.md) for the initial acceptance-work area.
