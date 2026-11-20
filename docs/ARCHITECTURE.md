# Architecture and purchase state

The React/Vite client calls FastAPI. SQLAlchemy persists accounts, revocable access sessions, merchants, products, agent sessions/messages, negotiations, inventory reservations, invoices, transactions, risk checks, and verified Nostr listing events in local SQLite.

## Purchase workflow

Buyer parsing → local inventory discovery → deterministic total calculation → persisted negotiation and message history → customer approval → atomic stock reservation → demo or LNbits invoice → provider status check. Product totals and risk checks are computed in Python. AI output cannot authorize payments.

Approval reserves `ceil(requested quantity)` stock units using a conditional SQL update. A reservation expires in one hour and is released by the database dependency on a later request. Provider-confirmed buyer payment changes an order to `PAYMENT_CONFIRMED`; merchant payout/settlement is not implemented, so it cannot become `COMPLETED`.

## Nostr

Merchant listing events use kind 30078 and `satoshibazaar/listing/v1`. A merchant wallet signs through NIP-07. FastAPI recomputes the NIP-01 event ID, verifies BIP-340 Schnorr signatures with coincurve, validates product content, sends the event to configured WebSocket relays, and stores it only after at least one relay acknowledges it. Relay-discovered listings remain external and are not treated as reserved local inventory.

## Authentication

Passwords use bcrypt. HS256 access tokens include a token ID and expiry; token IDs are stored so logout can revoke a session. CUSTOMER and MERCHANT writes use role dependencies and account ownership filters. ADMIN is not self-registrable and must be provisioned out of band. Development may use an ephemeral key if setup was bypassed; production startup requires `JWT_SECRET`.

## Schema evolution

New databases use SQLAlchemy `create_all`. Existing SQLite databases receive additive columns through `upgrade_existing_sqlite_schema`. This is a lightweight local migration and does not replace Alembic migrations for production or destructive schema changes.
