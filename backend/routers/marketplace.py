from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Product, Merchant
from schemas import MerchantCreate, MerchantOut, ProductCreate, ProductOut, MarketplaceItem
from typing import List, Optional
from auth import require_roles
from models import User

router = APIRouter(prefix="/api", tags=["marketplace"])


@router.get("/marketplace", response_model=List[MarketplaceItem])
def get_marketplace(search: Optional[str] = None, category: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Product, Merchant).join(Merchant, Product.merchant_id == Merchant.id)
    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))
    results = query.limit(100).all()
    items = []
    for product, merchant in results:
        items.append(MarketplaceItem(
            product_id=product.id,
            product_name=product.name,
            category=product.category,
            price_sats=product.price_sats,
            quantity_available=product.quantity_available,
            description=product.description or "",
            merchant_id=merchant.id,
            merchant_name=merchant.name,
            merchant_location=merchant.location,
            merchant_pubkey=merchant.pubkey,
            is_demo=product.is_demo,
            listing_source="demo_database" if product.is_demo else ("nostr_relay" if product.nostr_event_id else "local_database")
        ))
    return items


@router.post("/merchants", response_model=MerchantOut)
def create_merchant(data: MerchantCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("MERCHANT"))):
    if db.query(Merchant).filter(Merchant.owner_user_id == user.id).first():
        raise HTTPException(status_code=409, detail="This account already has a merchant profile")
    merchant = Merchant(**data.model_dump(exclude={"is_demo"}), owner_user_id=user.id, is_demo=False)
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    return merchant


@router.get("/merchants", response_model=List[MerchantOut])
def list_merchants(db: Session = Depends(get_db)):
    return db.query(Merchant).all()


@router.get("/merchants/me", response_model=Optional[MerchantOut])
def get_my_merchant(db: Session = Depends(get_db), user: User = Depends(require_roles("MERCHANT"))):
    return db.query(Merchant).filter(Merchant.owner_user_id == user.id).first()


@router.get("/merchants/{merchant_id}", response_model=MerchantOut)
def get_merchant(merchant_id: int, db: Session = Depends(get_db)):
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


@router.get("/products", response_model=List[ProductOut])
def list_products(merchant_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Product)
    if merchant_id is not None:
        query = query.filter(Product.merchant_id == merchant_id)
    return query.order_by(Product.created_at.desc()).limit(500).all()


@router.post("/products", response_model=ProductOut)
def create_product(data: ProductCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("MERCHANT"))):
    merchant = db.query(Merchant).filter(Merchant.id == data.merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    if merchant.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only add products to your merchant profile")
    if data.price_sats <= 0 or data.quantity_available < 0:
        raise HTTPException(status_code=422, detail="Price must be positive and stock cannot be negative")
    product = Product(**data.model_dump(exclude={"is_demo"}), is_demo=False)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("MERCHANT"))):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.merchant.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only edit products in your merchant profile")
    destination = db.query(Merchant).filter(Merchant.id == data.merchant_id).first()
    if not destination:
        raise HTTPException(status_code=404, detail="Merchant not found")
    if destination.owner_user_id != user.id or destination.id != product.merchant_id:
        raise HTTPException(status_code=403, detail="Products cannot be reassigned to another merchant")
    if data.price_sats <= 0 or data.quantity_available < 0:
        raise HTTPException(status_code=422, detail="Price must be positive and stock cannot be negative")
    for key, value in data.model_dump().items():
        setattr(product, key, value)
    product.is_demo = False
    db.commit()
    db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("MERCHANT"))):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.merchant.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only delete products in your merchant profile")
    db.delete(product)
    db.commit()
