# SatoshiBazaar

**Discover locally. Negotiate intelligently. Pay instantly.**

SatoshiBazaar is a local commerce MVP for Dakar, Senegal. It combines a React marketplace, FastAPI backend, SQLite persistence, a deterministic five-agent buying workflow, signed NIP-01 Nostr listings, customer/merchant accounts, inventory reservations, a safe demo mode, Alby NWC faucet sandbox, and gated LNbits testnet/live integrations.

## Start on Windows 11

Requirements: Python 3.11+, Node.js 20.19+ or 22.12+, npm, and PowerShell. The checked-in `.env.example` selects Alby faucet sandbox and needs two faucet wallet URLs before payments work. To run offline in simulated mode, set `PAYMENT_MODE=demo` in `.env`.

```powershell
cd D:\satoshibazaar
.\setup.ps1
.\run.ps1
```

Open http://localhost:5173. Backend: http://localhost:8000. API docs: http://localhost:8000/docs. Health: http://localhost:8000/health.

The setup script creates `backend/.venv`, installs backend/frontend dependencies, and copies `.env.example` to `.env`. No API keys are needed for local demo mode. To stop services started by `run.ps1`, stop the two Python/Node processes shown in `.run-logs/processes.json` using Task Manager or PowerShell.

## Manual startup

Terminal 1:

```powershell
cd <project-folder>\backend
..\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000 --env-file ..\\.env
```

Terminal 2:

```powershell
cd <project-folder>\frontend
npm.cmd run dev -- --host 127.0.0.1
```

## Demo scenario

In Negotiation, submit: “I need 10 kg of rice in Dakar for a maximum total of 250,000 sats.” On a clean database, the app seeds three DEMO merchants. Stored unit prices are 28,000, 27,000, and 24,000 sats/kg. BioFarm Direct offers 240,000 sats total; the remaining budget is 10,000 sats. The app requires customer approval before it creates a demo invoice reference. Demo invoices are not BOLT11 invoices and cannot receive Bitcoin. They remain pending and are never auto-marked paid.

## Current capabilities and limits

- React interface with Overview, Marketplace, Agent Arena, Negotiation, Lightning Wallet, Merchant Portal, Transactions, and Security Center sections.
- Persisted agent sessions/messages, offers based on saved product inventory, exact budget checks, explicit approval, local SQLite storage, and demo listings.
- Registration/login use bcrypt password hashing, expiring HS256 access tokens, revocable database sessions, and CUSTOMER/MERCHANT role checks. Sensitive routes are scoped to the authenticated account; ADMIN is provisioned out of band.
- Gemini parsing remains optional. To install the provider SDK, activate `backend/.venv` and run `python -m pip install -r requirements-ai.txt`; deterministic parsing works without it.
- NIP-01 event IDs and Schnorr signatures are verified with coincurve. Relay discovery/publication uses configured WebSockets; merchants sign through a NIP-07 browser extension. A listing is stored as relay-published only after an actual relay acknowledgement. Relay integration has not been live-tested here.
- Lightning payments support backend-selected `demo`, `testnet`, `live`, and `alby_sandbox` modes. Alby sandbox uses two distinct faucet NWC test wallets for merchant invoice creation and explicitly approved buyer payment; the backend verifies the exact payment independently through the merchant wallet. Configure only backend `.env` credentials. See [Lightning payment setup](docs/LIGHTNING_SETUP.md). Missing setup never falls back to another provider.
- Merchant inventory is atomically reserved when a customer approves; expired reservations are released on subsequent API requests. Merchant counteroffer/confirmation and settlement workflows are not implemented yet.
- This is not production-ready: do not expose it publicly until merchant settlement, operational rate limiting, production database migrations, monitoring, and external integration verification are complete.

See [BUILD_PROGRESS.md](BUILD_PROGRESS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [API_DOCUMENTATION.md](API_DOCUMENTATION.md), [SECURITY.md](SECURITY.md), and [DEPLOYMENT.md](DEPLOYMENT.md).
