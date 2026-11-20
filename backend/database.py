import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./satoshibazaar.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        from models import InventoryReservation, Product
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        expired = db.query(InventoryReservation).filter(
            InventoryReservation.status == "RESERVED",
            InventoryReservation.expires_at <= now,
        ).all()
        for reservation in expired:
            result = db.query(InventoryReservation).filter(
                InventoryReservation.id == reservation.id,
                InventoryReservation.status == "RESERVED",
            ).update({InventoryReservation.status: "RELEASED"}, synchronize_session=False)
            if result:
                db.query(Product).filter(Product.id == reservation.product_id).update(
                    {Product.quantity_available: Product.quantity_available + reservation.quantity},
                    synchronize_session=False,
                )
        if expired:
            db.commit()
        yield db
    finally:
        db.close()


def upgrade_existing_sqlite_schema(db_engine=engine):
    """Apply additive columns before create_all adds indexes to legacy tables."""
    if db_engine.dialect.name != "sqlite":
        return
    additions = {
        "users": {
            "password_hash": "VARCHAR(255)",
            "role": "VARCHAR(20) NOT NULL DEFAULT 'CUSTOMER'",
        },
        "merchants": {"owner_user_id": "INTEGER"},
        "products": {"nostr_event_id": "VARCHAR(64)"},
        "agent_sessions": {"user_id": "INTEGER"},
        "negotiations": {
            "buyer_user_id": "INTEGER",
            "requested_quantity": "FLOAT NOT NULL DEFAULT 1",
            "requested_unit": "VARCHAR(30) DEFAULT 'unit'",
        },
        "transactions": {
            "buyer_user_id": "INTEGER",
            "merchant_id": "INTEGER",
            "provider_name": "VARCHAR(40) NOT NULL DEFAULT 'legacy'",
            "environment": "VARCHAR(16) NOT NULL DEFAULT 'legacy'",
            "amount_msat": "INTEGER",
            "buyer_wallet_alias": "VARCHAR(80)",
            "merchant_wallet_alias": "VARCHAR(80)",
        },
        "risk_checks": {"buyer_user_id": "INTEGER"},
        "payment_invoices": {
            "checking_id": "VARCHAR(255)",
            "payment_mode": "VARCHAR(12) NOT NULL DEFAULT 'legacy'",
            "merchant_id": "INTEGER",
            "provider_name": "VARCHAR(40) NOT NULL DEFAULT 'legacy'",
            "environment": "VARCHAR(16) NOT NULL DEFAULT 'legacy'",
            "verified_at": "DATETIME",
            "amount_msat": "INTEGER",
            "buyer_wallet_alias": "VARCHAR(80)",
            "merchant_wallet_alias": "VARCHAR(80)",
            "payment_attempted_at": "DATETIME",
        },
    }
    inspector = inspect(db_engine)
    present_tables = set(inspector.get_table_names())
    current_columns = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in additions if table in present_tables
    }
    with db_engine.begin() as connection:
        for table, columns in additions.items():
            if table not in present_tables:
                continue
            for name, definition in columns.items():
                if name not in current_columns[table]:
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'))
        if "payment_invoices" in present_tables and "payment_mode" not in current_columns.get("payment_invoices", set()):
            connection.execute(text("UPDATE payment_invoices SET payment_mode = CASE WHEN is_demo = 1 THEN 'demo' ELSE 'legacy' END"))
        if "transactions" in present_tables:
            connection.execute(text("UPDATE transactions SET mode = 'legacy' WHERE mode = 'lightning'"))
            connection.execute(text("UPDATE transactions SET environment = mode WHERE environment = 'legacy' AND mode IN ('demo', 'testnet', 'live')"))
            connection.execute(text("UPDATE transactions SET provider_name = CASE mode WHEN 'demo' THEN 'demo_simulator' WHEN 'testnet' THEN 'lnbits_testnet' WHEN 'live' THEN 'lnbits_live' ELSE 'legacy' END WHERE provider_name = 'legacy'"))
        if "payment_invoices" in present_tables:
            connection.execute(text("UPDATE payment_invoices SET environment = payment_mode WHERE environment = 'legacy' AND payment_mode IN ('demo', 'testnet', 'live')"))
            connection.execute(text("UPDATE payment_invoices SET provider_name = CASE payment_mode WHEN 'demo' THEN 'demo_simulator' WHEN 'testnet' THEN 'lnbits_testnet' WHEN 'live' THEN 'lnbits_live' ELSE 'legacy' END WHERE provider_name = 'legacy'"))
