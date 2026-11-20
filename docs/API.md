# API overview

Interactive OpenAPI: `http://localhost:8000/docs`. Sensitive routes use `Authorization: Bearer <access_token>`.

- Auth: `/api/auth/register`, `/login`, `/me`, `/logout`.
- Marketplace: `/api/marketplace`, `/api/merchants`, `/api/merchants/me`, `/api/products`.
- Agents: `/api/agents/run`, `/api/agents/sessions` and session message routes.
- Negotiations: `/api/negotiations/{id}`, `/approve`, `/reject`.
- Nostr: `/api/nostr/status`, `/merchants`, `/listings/unsigned`, `/publish`.
- Lightning: `/api/lightning/invoices` and `/invoices/{invoice_id}`.
- Transactions and risk: `/api/transactions`, `/api/security/checks`.

Authorization rules: buyers own their sessions, negotiations, invoices, transactions, and security history. Merchants can edit only their own profile and products. Public marketplace and merchant endpoints are read-only.

The full route table is maintained in [API_DOCUMENTATION.md](../API_DOCUMENTATION.md).
