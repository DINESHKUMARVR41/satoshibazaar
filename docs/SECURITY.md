# Security guide

- Generate a unique high-entropy `JWT_SECRET`; the setup script replaces the example placeholder for local use. In production, inject the key using a secret manager and set `APP_ENV=production`.
- Passwords are bcrypt hashed. Tokens expire and are associated with revocable database session records.
- Register only CUSTOMER or MERCHANT accounts. ADMIN accounts must be provisioned out of band.
- Keep `.env`, LNbits keys, and any wallet configuration out of source control and browser settings.
- Nostr event public keys/signatures are public protocol data. Private keys stay in a NIP-07 wallet; the server accepts signed events and verifies them.
- LNbits invoice credentials are used only by the backend. The code never treats a client-provided success state as authoritative.
- Incoming payment confirmation is not merchant settlement. No payout or escrow is implemented.

Authentication throttling is in-memory per process. Before public deployment, add shared rate limiting, monitoring, TLS, audit retention controls, backups, Alembic migrations, and an operational incident process. See [SECURITY.md](../SECURITY.md).
