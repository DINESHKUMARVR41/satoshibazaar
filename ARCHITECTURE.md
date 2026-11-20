# Architecture

## Runtime

- `frontend/`: React + Vite single-page application. Axios calls the FastAPI service at `VITE_API_URL` (default `http://localhost:8000`).
- `backend/`: FastAPI routers, SQLAlchemy models, deterministic buyer/discovery/merchant/negotiation/risk agents, and Lightning/Nostr service modules.
- `backend/satoshibazaar.db`: local SQLite file created relative to the backend working directory. Tables and demo seed data initialize at API startup.

## Purchase workflow

1. Buyer Agent parses product, requested quantity/unit, maximum total budget, and location.
2. Discovery Agent searches persisted inventory with enough stock for the requested quantity.
3. Merchant Agent reads saved unit prices and computes total price from quantity.
4. Negotiation Agent compares totals and persists a negotiation plus the three-round history.
5. Risk Guardian independently validates positive amount, configured transaction ceiling, accepted negotiation, exact amount match, buyer budget, duplicate paid invoice, and customer approval. The first workflow pass records approval as pending; invoice creation requires it to pass.
6. Customer approval is recorded by the backend. Only then can an invoice be requested.
7. `PAYMENT_MODE` selects demo, testnet, or live on the backend. Demo creates simulated, non-payable references. Testnet/live require distinct LNbits URLs and keys, validate the BOLT11 network and amount, and check payment status with the matching provider.
8. Buyer payment confirmation does not complete an order. A merchant submits an exact amount invoice on the same network; backend-only LNbits Admin credentials send the payout. The transaction completes only after a separate provider status check confirms settlement. Ambiguous outgoing timeouts are held for manual reconciliation and cannot be automatically retried.

## Persistence

SQLAlchemy models live in `backend/models.py`; tables are created on startup using `Base.metadata.create_all`. Existing SQLite payment rows are additively labeled `legacy` when their environment cannot be established. Invoice, transaction, and settlement rows retain a mode label and are not relabeled across networks. Back up the SQLite file before manual schema changes. Use a migration tool and a persistent managed database for deployment.

## External integrations

Gemini is optional for buyer parsing; deterministic parsing is the no-key fallback. LNbits is optional and configured only on the backend with mode-specific credentials. Nostr connectivity depends on configured relays and signer availability. Do not interpret local demo event records as signed or relay-acknowledged Nostr events.
