from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, or_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import List, Optional, Dict

# === SETUP === #

app = FastAPI(title="Rewoven Admin API", version="1.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = "sqlite:///./rewoven_admin.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# === MODELS === #

class AdminUser(Base):
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    role = Column(String(20), default="Customer")  # Admin, Seller, Customer
    details = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("admin_users.id"))
    item_id = Column(String(100), nullable=False)
    status = Column(String(20), default="pending")  # pending/shipped/completed
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# === UTILS === #

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# === USERS === #

@app.get("/api/admin/users/", response_model=List[Dict])
def get_users(db: Session = Depends(get_db)):
    users = db.query(AdminUser).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "details": u.details,
            "created_at": u.created_at
        }
        for u in users
    ]

@app.post("/api/admin/users/")
def create_user(user: Dict, db: Session = Depends(get_db)):
    new_user = AdminUser(**user)
    db.add(new_user)
    db.commit()
    return {"message": "User created successfully"}

@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db.query(AdminUser).filter_by(id=user_id).delete()
    db.commit()
    return {"message": "User deleted"}

@app.patch("/api/admin/users/{user_id}/promote")
def promote_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(AdminUser).get(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.role = "Admin"
    db.commit()
    return {"message": f"{user.name} promoted to Admin"}

@app.get("/api/admin/users/search")
def search_users(q: str, db: Session = Depends(get_db)):
    results = db.query(AdminUser).filter(
        or_(AdminUser.name.ilike(f"%{q}%"), AdminUser.email.ilike(f"%{q}%"), AdminUser.role.ilike(f"%{q}%"))
    ).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "details": u.details,
            "created_at": u.created_at
        }
        for u in results
    ]

# === ORDERS === #

@app.get("/api/admin/orders/", response_model=List[Dict])
def get_orders(db: Session = Depends(get_db)):
    orders = db.query(Order).all()
    return [
        {
            "id": o.id,
            "user_id": o.user_id,
            "item_id": o.item_id,
            "status": o.status,
            "created_at": o.created_at
        }
        for o in orders
    ]

@app.post("/api/admin/orders/")
def create_order(order: Dict, db: Session = Depends(get_db)):
    new_order = Order(**order)
    db.add(new_order)
    db.commit()
    return {"message": "Order created successfully"}

@app.patch("/api/admin/orders/{order_id}/status")
def update_order_status(order_id: int, status: str, db: Session = Depends(get_db)):
    order = db.query(Order).get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    order.status = status
    db.commit()
    return {"message": f"Order #{order.id} status updated to {status}"}

# === HEALTH CHECK === #

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow()}

# === RUN === #

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)