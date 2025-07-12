# Add these models to your existing database models

from sqlalchemy import Column, Integer, String, DateTime, Text, Enum
from datetime import datetime
import enum

class TransactionType(enum.Enum):
    UPLOAD = "upload"
    REDEEM = "redeem"
    SWAP = "swap"
    ADMIN_BONUS = "admin_bonus"
    MILESTONE = "milestone"

class UserPoints(Base):
    __tablename__ = "user_points"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), unique=True, nullable=False)
    total_points = Column(Integer, default=0)
    uploads_count = Column(Integer, default=0)
    redeems_count = Column(Integer, default=0)
    swaps_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PointTransaction(Base):
    __tablename__ = "point_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    points_change = Column(Integer, nullable=False)  # +5, -10, +2, etc.
    description = Column(String(255))
    related_item_id = Column(String(100))  # Optional: link to item
    created_at = Column(DateTime, default=datetime.utcnow)

# Pydantic models
class UserPointsResponse(BaseModel):
    user_id: str
    total_points: int
    uploads_count: int
    redeems_count: int
    swaps_count: int

class PointTransactionResponse(BaseModel):
    id: int
    transaction_type: str
    points_change: int
    description: str
    created_at: datetime

class ModifyPointsRequest(BaseModel):
    points: int
    reason: str

# Points configuration
POINTS_CONFIG = {
    "upload": 5,
    "redeem": -10,
    "swap": 2,
    "milestone_10": 10,
    "milestone_20": 25,
    "milestone_50": 50
}

# Helper functions
def get_user_points(db: Session, user_id: str) -> UserPoints:
    """Get or create user points record"""
    user_points = db.query(UserPoints).filter(UserPoints.user_id == user_id).first()
    if not user_points:
        user_points = UserPoints(user_id=user_id)
        db.add(user_points)
        db.commit()
        db.refresh(user_points)
    return user_points

def add_points_transaction(db: Session, user_id: str, transaction_type: TransactionType, 
                         points: int, description: str = None, item_id: str = None):
    """Add a points transaction and update user balance"""
    
    # Get user points
    user_points = get_user_points(db, user_id)
    
    # Create transaction record
    transaction = PointTransaction(
        user_id=user_id,
        transaction_type=transaction_type,
        points_change=points,
        description=description,
        related_item_id=item_id
    )
    db.add(transaction)
    
    # Update user points
    user_points.total_points += points
    user_points.updated_at = datetime.utcnow()
    
    # Update counters
    if transaction_type == TransactionType.UPLOAD:
        user_points.uploads_count += 1
        # Check for milestone bonuses
        if user_points.uploads_count in [10, 20, 50]:
            milestone_points = POINTS_CONFIG.get(f"milestone_{user_points.uploads_count}", 0)
            if milestone_points > 0:
                milestone_transaction = PointTransaction(
                    user_id=user_id,
                    transaction_type=TransactionType.MILESTONE,
                    points_change=milestone_points,
                    description=f"Milestone bonus: {user_points.uploads_count} uploads"
                )
                db.add(milestone_transaction)
                user_points.total_points += milestone_points
    
    elif transaction_type == TransactionType.REDEEM:
        user_points.redeems_count += 1
    elif transaction_type == TransactionType.SWAP:
        user_points.swaps_count += 1
    
    db.commit()
    return transaction

# API Endpoints

@app.get("/api/users/{user_id}/points", response_model=UserPointsResponse)
async def get_user_points_endpoint(user_id: str, db: Session = Depends(get_db)):
    """Get user points balance and stats"""
    user_points = get_user_points(db, user_id)
    return UserPointsResponse(
        user_id=user_points.user_id,
        total_points=user_points.total_points,
        uploads_count=user_points.uploads_count,
        redeems_count=user_points.redeems_count,
        swaps_count=user_points.swaps_count
    )

@app.get("/api/users/{user_id}/transactions", response_model=List[PointTransactionResponse])
async def get_user_transactions(user_id: str, limit: int = 50, db: Session = Depends(get_db)):
    """Get user's points transaction history"""
    transactions = db.query(PointTransaction).filter(
        PointTransaction.user_id == user_id
    ).order_by(PointTransaction.created_at.desc()).limit(limit).all()
    
    return [
        PointTransactionResponse(
            id=t.id,
            transaction_type=t.transaction_type.value,
            points_change=t.points_change,
            description=t.description or "",
            created_at=t.created_at
        )
        for t in transactions
    ]

@app.post("/api/users/{user_id}/points/modify")
async def modify_user_points(
    user_id: str, 
    request: ModifyPointsRequest,
    admin_user_id: str = Form(...),  # Admin authentication
    db: Session = Depends(get_db)
):
    """Admin endpoint to modify user points"""
    
    # Simple admin check (implement proper auth)
    if admin_user_id != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    transaction = add_points_transaction(
        db, user_id, TransactionType.ADMIN_BONUS, 
        request.points, f"Admin: {request.reason}"
    )
    
    return {"message": "Points modified successfully", "transaction_id": transaction.id}

@app.post("/api/items/{item_id}/redeem")
async def redeem_item(
    item_id: str,
    user_id: str = Form(...),
    db: Session = Depends(get_db)
):
    """Redeem an item using points"""
    
    # Check if user has enough points
    user_points = get_user_points(db, user_id)
    redeem_cost = abs(POINTS_CONFIG["redeem"])
    
    if user_points.total_points < redeem_cost:
        raise HTTPException(
            status_code=400, 
            detail=f"Insufficient points. Need {redeem_cost}, have {user_points.total_points}"
        )
    
    # Get item
    item = db.query(ClothingItem).filter(ClothingItem.item_id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    if item.status != "active":
        raise HTTPException(status_code=400, detail="Item not available")
    
    # Deduct points
    add_points_transaction(
        db, user_id, TransactionType.REDEEM, 
        POINTS_CONFIG["redeem"], f"Redeemed: {item.title}", item_id
    )
    
    # Mark item as redeemed
    item.status = "redeemed"
    db.commit()
    
    return {"message": "Item redeemed successfully", "points_spent": redeem_cost}

# Modify existing upload endpoint to add points
@app.post("/api/upload/", response_model=ImageUploadResponse)
async def upload_image_with_points(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    db: Session = Depends(get_db)
):
    """Upload image and earn points"""
    
    # ... existing upload logic ...
    
    # Award points for upload
    add_points_transaction(
        db, user_id, TransactionType.UPLOAD, 
        POINTS_CONFIG["upload"], "Uploaded new item"
    )
    
    # ... return response ...

# Modify existing item creation to include points
@app.post("/api/items/", response_model=ItemResponse)
async def create_item_with_points(
    item: ItemCreate,
    user_id: str = Form(...),
    db: Session = Depends(get_db)
):
    """Create item (points already awarded during upload)"""
    
    # ... existing item creation logic ...
    
    return response

# Complete swap endpoint
@app.post("/api/swaps/{swap_id}/complete")
async def complete_swap(
    swap_id: str,
    user1_id: str = Form(...),
    user2_id: str = Form(...),
    db: Session = Depends(get_db)
):
    """Complete a successful swap and award points"""
    
    # Award points to both users
    add_points_transaction(
        db, user1_id, TransactionType.SWAP, 
        POINTS_CONFIG["swap"], f"Completed swap: {swap_id}"
    )
    add_points_transaction(
        db, user2_id, TransactionType.SWAP, 
        POINTS_CONFIG["swap"], f"Completed swap: {swap_id}"
    )
    
    return {"message": "Swap completed, points awarded"}

# Update tables creation
Base.metadata.create_all(bind=engine)

# Usage Examples:
"""
# Get user points
GET /api/users/user123/points

# Get transaction history
GET /api/users/user123/transactions?limit=20

# Redeem an item
POST /api/items/item456/redeem
Form: user_id=user123

# Admin modify points
POST /api/users/user123/points/modify
Form: admin_user_id=admin
JSON: {"points": 50, "reason": "Bonus for good behavior"}

# Complete swap
POST /api/swaps/swap789/complete
Form: user1_id=user123&user2_id=user456
"""
