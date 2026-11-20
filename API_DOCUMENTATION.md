# API reference

Base URL: `http://localhost:8000`. Interactive OpenAPI docs: `/docs`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Backend and provider mode summary; never returns secrets |
| POST | `/api/auth/register` | Register CUSTOMER or MERCHANT and receive an access token |
| POST | `/api/auth/login` | Verify credentials and create a revocable token session |
| GET | `/api/auth/me` | Return the authenticated account |
| POST | `/api/auth/logout` | Revoke the current session token |
| GET | `/api/marketplace?search=&category=` | Search stored product/merchant listings |
| GET, POST | `/api/merchants` | List or create a demo merchant |
| GET | `/api/merchants/{merchant_id}` | Merchant detail |
| GET | `/api/merchants/me` | Authenticated merchant's own profile |
| GET | `/api/products?merchant_id=` | List stored products |
| POST, PUT, DELETE | `/api/products[/{product_id}]` | Create/update/delete product listing |
| POST | `/api/agents/run` | Run and persist the buyer-to-risk workflow |
| GET | `/api/agents/sessions` | List persisted sessions |
| GET | `/api/agents/sessions/{session_id}` | Session detail |
| GET | `/api/agents/sessions/{session_id}/messages` | Persisted agent message history |
| GET | `/api/negotiations/{negotiation_id}` | Negotiation detail and rounds |
| POST | `/api/negotiations/{negotiation_id}/approve` | Record customer approval for accepted in-budget offer |
| POST | `/api/negotiations/{negotiation_id}/reject` | Reject an unapproved offer |
| GET | `/api/nostr/status` | Relay configuration and reachability probes |
| GET | `/api/nostr/merchants` | Fetch, verify, deduplicate, and cache relay listings |
| GET | `/api/nostr/listings/unsigned?product_id=` | Return an unsigned event for NIP-07 signing by the owning merchant |
| POST | `/api/nostr/publish` | Verify a signed event and publish to configured relays |
| POST | `/api/lightning/invoices` | Create a demo invoice reference or provider invoice after risk checks |
| GET | `/api/lightning/invoices/{invoice_id}` | Poll invoice/payment status |
| GET | `/api/transactions` | Recent transaction records |
| GET | `/api/security/checks` | Risk Guardian audit checks |

All sensitive endpoints require a Bearer token. CUSTOMER endpoints are scoped to the account; merchant writes require MERCHANT role and profile ownership; ADMIN access is provisioned out of band. Public marketplace and merchant listings are read-only. Demo Nostr records are marked invalid and are not returned as relay-verified listings. Real relay connectivity is environment-dependent.

Transactions show `PAYMENT_CONFIRMED` after LNbits independently confirms the incoming invoice and amount. Merchant payout settlement is not implemented, so the API never marks these orders `COMPLETED`.
