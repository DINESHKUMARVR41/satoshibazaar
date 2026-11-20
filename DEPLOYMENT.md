# Deployment

The project is configured for local Windows development. Authentication, payment mode isolation, and merchant settlement verification are implemented. Persistent database migrations and production operational controls still need deployment-specific review before processing valuable funds.

## Frontend on Vercel

- Set the project root to `frontend`.
- Build command: `npm run build`; output: `dist`.
- Set `VITE_API_URL` to the HTTPS backend URL.
- Restrict backend CORS to the deployed frontend origin.

## Backend on Render or similar

- Root directory: repository root; build command: `pip install -r backend/requirements.txt`.
- Start command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`.
- Set `PAYMENT_MODE=demo` by default. For testnet or live, configure only that mode's dedicated `LNBITS_*_URL`, `LNBITS_*_INVOICE_KEY`, and `LNBITS_*_ADMIN_KEY` values in the host secret manager. Never use frontend variables or committed files.
- Set a strong `JWT_SECRET`, `APP_ENV=production`, and exact `ALLOWED_ORIGINS` values in the host secret/configuration manager.
- SQLite on ephemeral instances is not persistent. Attach a persistent disk or migrate to PostgreSQL and configure backups before production.
- Use HTTPS, restrict CORS, set transaction limits, and only enable LNbits after validating invoice/status responses against a test wallet.

## Optional integrations

`GEMINI_API_KEY` is optional. LNbits credentials are mode-specific and backend-only; do not expose them to React. Testnet and live must use distinct wallets and networks. A provider's configuration status does not prove a payment occurred; only a payment status confirmed by that provider does.
