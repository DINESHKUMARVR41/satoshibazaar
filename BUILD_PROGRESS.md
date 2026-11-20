# SatoshiBazaar build progress

This is an incremental completion of the existing React/FastAPI project. It is a tested local MVP, **not a production-ready marketplace yet**. Live LNbits credentials and external relay network access were unavailable for live integration checks.

## Existing work preserved

- React/Vite visual system and eight sections: Overview, Marketplace, Agent Arena, Negotiation, Lightning Wallet, Merchant Portal, Transactions, Security Center.
- FastAPI/SQLAlchemy/SQLite backend and five distinct deterministic agent modules.
- Existing local merchant/product seed and the 10 kg rice demo scenario.
- Existing API-driven dashboard, agent message history, and demo payment separation.

## Implemented in this continuation

- [x] Customer/merchant registration and login, bcrypt password hashing, HS256 expiring access tokens, revocable stored token sessions, `/me`, and logout.
- [x] Customer/merchant role checks for sensitive write routes, buyer session/negotiation/invoice/transaction ownership filters, and merchant product ownership checks.
- [x] In-memory auth throttling (8 attempts/IP/minute/process) and production startup enforcement for `JWT_SECRET`.
- [x] SQLite additive schema migration for existing databases and setup-time DB initialization/demo seed.
- [x] Atomic inventory reservation on approval, stock conflict rejection, and expiry release on subsequent API requests.
- [x] NIP-01 canonical event ID and BIP-340 Schnorr validation using coincurve; configurable WebSocket relays; NIP-07 signed product publication; relay acknowledgement checks; verified, deduplicated relay discovery; local marketplace keeps working when relays fail.
- [x] Separate Demo, Testnet, and Live payment providers selected by backend `PAYMENT_MODE`; dedicated testnet/live credentials, URL/key separation, strict BOLT11 network and amount checks, and no fallback.
- [x] LNbits incoming invoice request and independent status verification with checking ID and exact amount. Provider intent is persisted before outbound creation; mode is stored on each invoice and transaction. Buyer payment confirmation remains settlement-pending and never marks an order complete.
- [x] Merchant settlement endpoint with same-network/exact-amount invoice validation, backend-only Admin-key payout, independent outgoing status check, duplicate-send prevention, and ambiguous timeout review state.
- [x] Merchant UI for NIP-07 publish and Marketplace relay discovery.
- [x] Frontend displays the active backend payment mode in the signed-in workspace and authentication screen; Demo invoices and simulated payments are explicitly labeled.
- [x] Documentation under `docs/` for API, architecture, security, Nostr, Lightning, deployment, and tests.

## Current verification

- [x] Backend suite includes authentication/authorization, authenticated rice purchase, inventory reservation, Nostr checks, mocked LNbits network/amount/status validation, expired invoices, duplicate simulation/status checks, and successful/failed merchant settlement checks (20 passed).
- [x] Frontend production build succeeds after auth, Nostr, and payment mode updates.
- [ ] Full account and browser smoke check after the mode changes remains pending.
- [ ] Windows setup/run scripts parse check and clean extraction test are pending.
- [ ] Rebuild the ZIP after all source/docs/test updates.

## Remaining before production-ready

- [ ] Merchant counteroffers and merchant confirmation are not implemented as persisted live response workflows; the negotiation logic still selects from catalog quotes.
- [ ] Refunds and escrow are not implemented. Ambiguous payout timeouts require manual LNbits reconciliation.
- [ ] Testnet/live were not connected to actual wallets in this environment. Configure their dedicated credentials before use; no testnet or live payment has been made or verified here.
- [ ] Nostr relay connectivity and publication were not live-tested here. Nostr publishing requires a usable NIP-07 extension in the browser.
- [x] LNbits integration paths were tested with mocked requests; actual wallet/backend connectivity still requires dedicated credentials and testnet/live verification.
- [ ] Frontend automated tests, accessibility/browser automation, product image upload, profile editing, and account recovery are missing.
- [ ] No Alembic migration environment yet. SQLite additive migration is local-only; PostgreSQL compatibility and concurrency have not been tested.
- [ ] Admin is not self-registrable and must be provisioned out of band; there is no admin management UI.
- [ ] Production shared rate limiting, monitoring/alerting, structured audit retention, TLS/deployment review, and operational settlement recovery remain.

## References

- NIP-01 event format and signature requirements: <https://github.com/nostr-protocol/nips/blob/master/01.md>
- LNbits Payments API: <https://docs.lnbits.com/api/core/payments>
