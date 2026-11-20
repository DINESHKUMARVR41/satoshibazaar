# Security notes

## Implemented safeguards

- Passwords are bcrypt hashed, JWT access tokens are signed with HS256 and expire, and session records can be revoked by logout.
- Role checks protect merchant profile/product writes, buyer workflows, negotiations, invoices, transactions, and risk history. Merchant product mutation checks ownership; customer purchase data is scoped by authenticated user ID.
- Registration/login are throttled to eight attempts per client IP per minute in each backend process.
- No frontend configuration contains LNbits credentials.
- Real invoice mode fails closed if LNbits is not configured or invoice creation fails. It never substitutes a fabricated BOLT11 string or silently falls back to demo.
- Demo invoice IDs are explicitly `DEMO-SIMULATED-NOT-PAYABLE-*` references; a separately labeled local simulation is the only way they reach `SIMULATED_PAID`.
- `PAYMENT_MODE` is selected on the backend and included in invoice, transaction, and settlement records. Testnet/live providers use separate credentials and validate the returned BOLT11 network and amount. Missing configuration fails closed without a demo fallback.
- LNbits Admin keys are backend-only and used for merchant payouts. Payment completion requires a separate status check from the matching LNbits wallet. Ambiguous payout timeouts are blocked from automatic retry.
- Backend Risk Guardian checks amount positivity, hard transaction cap, accepted negotiation state, negotiated amount, budget, duplicate paid invoices, and explicit customer approval.
- Approval endpoint only accepts a negotiated offer within the buyer’s maximum budget.
- Agent offers use database product pricing and requested quantity; discovery checks available stock.
- Provider status errors do not mark a payment as paid.

## Limitations before production

- CORS defaults to the local Vite origin and reads a comma-separated `ALLOWED_ORIGINS` value; set the deployed frontend origin before deployment.
- Rate limiting is per-process memory state and is not a substitute for a shared production limiter. JWT secrets must be generated and managed through deployment secrets.
- Nostr relay connections and LNbits status/payment flows are implemented but have not been live-tested in this environment. Only verified, relay-acknowledged events are exposed as external listings.
- Add Alembic migrations, structured audit retention, secrets management, TLS, and deployment-specific transaction limits before public exposure.
- Merchant payout/settlement is not implemented. Incoming customer payment confirmation must not be mistaken for merchant settlement or order completion.
- Current LNbits integration has not been exercised with live credentials. Test on a non-production wallet first and verify provider responses and invoice expiry semantics.
