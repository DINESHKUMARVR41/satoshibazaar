from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import engine, SessionLocal, Base, upgrade_existing_sqlite_schema
from routers import marketplace, agents, negotiations, lightning, transactions, security, auth, nostr, settlements
import models
from seed import run_seed
from datetime import datetime, timezone
import os
from services.payment_providers import active_payment_mode, build_provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    upgrade_existing_sqlite_schema(engine)
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Seed data
    db = SessionLocal()
    try:
        build_provider(active_payment_mode())  # Validate the selected mode and its URL at startup.
        run_seed(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="SatoshiBazaar API",
    description="AI-Powered Local Commerce Network Using Nostr, Bitcoin Lightning and Autonomous Agents",
    version="1.0.0",
    lifespan=lifespan
)

_allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174").split(",")
    if origin.strip()
]
_local_dev_origin_regex = (
    r"^http://(localhost|127\.0\.0\.1):\d+$"
    if os.getenv("APP_ENV", "development").lower() != "production"
    else None
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_local_dev_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(marketplace.router)
app.include_router(agents.router)
app.include_router(negotiations.router)
app.include_router(lightning.router)
app.include_router(transactions.router)
app.include_router(security.router)
app.include_router(auth.router)
app.include_router(nostr.router)
app.include_router(settlements.router)


@app.get("/health")
def health():
    mode = active_payment_mode()
    provider = build_provider(mode)
    configured = provider.configured
    blockers = [] if mode == "demo" else ([] if configured else [f"Configure the dedicated {mode} LNbits URL, invoice key, and Admin key."])
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payment_mode": mode,
        "mode": mode.upper(),
        "demo_mode": mode == "demo",
        "payment_provider_configured": configured,
        "payment_network": provider.network,
        "payment_settlement_enabled": configured if mode != "demo" else True,
        "payment_mode_blockers": blockers,
        "version": "1.0.0",
        "services": {
            "lightning": "simulated" if mode == "demo" else f"lnbits_{mode}_{'configured' if configured else 'unconfigured'}",
            "nostr": "demo",
            "ai": "gemini" if os.getenv("GEMINI_API_KEY") else "fallback"
        }
    }
