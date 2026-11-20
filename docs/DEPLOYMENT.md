# Deployment guide

Frontend: deploy `frontend` to Vercel with `VITE_API_URL` pointing to the HTTPS API. Backend: install `backend/requirements.txt`, then run `uvicorn main:app --host 0.0.0.0 --port $PORT` from `backend`.

Set `JWT_SECRET`, `APP_ENV=production`, `ALLOWED_ORIGINS`, database URL, and optional provider secrets with the hosting provider's secret manager. Do not put LNbits keys in frontend variables. SQLite on ephemeral Render storage is not durable; use PostgreSQL plus migrations and backups in production.

This project still lacks merchant payout settlement and production Alembic migrations. The local SQLite schema adapter is not a production migration system. Do not present buyer payment as merchant settlement.
