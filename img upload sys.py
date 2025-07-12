# requirements.txt
"""
fastapi==0.104.1
uvicorn==0.24.0
python-multipart==0.0.6
pillow==10.0.1
sqlalchemy==2.0.23
sqlite3 (built-in)
"""

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from PIL import Image
import uuid
import os
import shutil
from pathlib import Path

# FastAPI app
app = FastAPI(title="Simple Marketplace API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup (SQLite for simplicity)
DATABASE_URL = "sqlite:///./marketplace.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# File upload configuration
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
(UPLOAD_DIR / "images").mkdir(exist_ok=True)
(UPLOAD_DIR / "thumbnails").mkdir(exist_ok=True)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

# Mount static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ==================== DATABASE MODELS ====================

class ClothingCategory(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    subcategories = Column(Text)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)

class ImageMetadata(Base):
    __tablename__ = "images"
    
    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(String(100), unique=True, nullable=False)
    original_name = Column(String(255), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    width = Column(Integer)
    height = Column(Integer)
    thumbnail_path = Column(String(500))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    uploaded_by = Column(String(100), nullable=False)

class ClothingItem(Base):
    __tablename__ = "items"
    
    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(String(100), unique=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Float, nullable=False)
    category = Column(String(100), nullable=False)
    condition = Column(String(50), nullable=False)
    brand = Column(String(100))
    size = Column(String(20))
    color = Column(String(50))
    location = Column(String(200))
    seller_id = Column(String(100), nullable=False)
    image_ids = Column(Text)  # JSON string of image IDs
    status = Column(String(20), default='active')
    views = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

# ==================== PYDANTIC MODELS ====================

class CategoryCreate(BaseModel):
    name: str
    subcategories: List[str] = []

class CategoryResponse(BaseModel):
    id: int
    name: str
    subcategories: List[str]
    created_at: datetime

class ImageUploadResponse(BaseModel):
    image_id: str
    original_name: str
    file_size: int
    dimensions: Dict[str, int]
    url: str
    thumbnail_url: str

class ItemCreate(BaseModel):
    title: str
    description: str
    price: float
    category: str
    condition: str
    brand: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    location: Optional[str] = None
    image_ids: List[str] = []

class ItemResponse(BaseModel):
    id: int
    item_id: str
    title: str
    description: str
    price: float
    category: str
    condition: str
    brand: Optional[str]
    size: Optional[str]
    color: Optional[str]
    location: Optional[str]
    seller_id: str
    status: str
    views: int
    created_at: datetime
    images: List[Dict[str, Any]] = []

# ==================== HELPER FUNCTIONS ====================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def validate_file(file: UploadFile) -> bool:
    """Simple file validation"""
    if file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")
    
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file format")
    
    return True

def create_thumbnail(image_path: str, thumbnail_path: str, size: tuple = (300, 300)) -> bool:
    """Create a simple thumbnail"""
    try:
        with Image.open(image_path) as img:
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(thumbnail_path, "JPEG", quality=85)
        return True
    except Exception as e:
        print(f"Error creating thumbnail: {e}")
        return False

# ==================== API ENDPOINTS ====================

@app.post("/api/categories/", response_model=CategoryResponse)
async def create_category(category: CategoryCreate, db: Session = Depends(get_db)):
    """Create a new clothing category"""
    
    # Check if category exists
    existing = db.query(ClothingCategory).filter(ClothingCategory.name == category.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category already exists")
    
    import json
    db_category = ClothingCategory(
        name=category.name,
        subcategories=json.dumps(category.subcategories)
    )
    
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    
    return CategoryResponse(
        id=db_category.id,
        name=db_category.name,
        subcategories=json.loads(db_category.subcategories or "[]"),
        created_at=db_category.created_at
    )

@app.get("/api/categories/", response_model=List[CategoryResponse])
async def get_categories(db: Session = Depends(get_db)):
    """Get all categories"""
    import json
    categories = db.query(ClothingCategory).all()
    
    return [
        CategoryResponse(
            id=cat.id,
            name=cat.name,
            subcategories=json.loads(cat.subcategories or "[]"),
            created_at=cat.created_at
        )
        for cat in categories
    ]

@app.post("/api/upload/", response_model=ImageUploadResponse)
async def upload_image(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    db: Session = Depends(get_db)
):
    """Upload an image"""
    
    # Validate file
    validate_file(file)
    
    # Generate unique image ID
    image_id = str(uuid.uuid4())
    
    # Create file paths
    file_ext = Path(file.filename).suffix.lower()
    file_name = f"{image_id}{file_ext}"
    image_path = UPLOAD_DIR / "images" / file_name
    thumbnail_name = f"{image_id}_thumb.jpg"
    thumbnail_path = UPLOAD_DIR / "thumbnails" / thumbnail_name
    
    # Save original image
    with open(image_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Get image dimensions
    with Image.open(image_path) as img:
        width, height = img.size
    
    # Create thumbnail
    create_thumbnail(str(image_path), str(thumbnail_path))
    
    # Save to database
    db_image = ImageMetadata(
        image_id=image_id,
        original_name=file.filename,
        file_name=file_name,
        file_size=file.size,
        width=width,
        height=height,
        thumbnail_path=thumbnail_name,
        uploaded_by=user_id
    )
    
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    
    return ImageUploadResponse(
        image_id=image_id,
        original_name=file.filename,
        file_size=file.size,
        dimensions={"width": width, "height": height},
        url=f"/uploads/images/{file_name}",
        thumbnail_url=f"/uploads/thumbnails/{thumbnail_name}"
    )

@app.post("/api/items/", response_model=ItemResponse)
async def create_item(
    item: ItemCreate,
    user_id: str = Form(...),
    db: Session = Depends(get_db)
):
    """Create a new clothing item"""
    
    import json
    
    # Generate unique item ID
    item_id = str(uuid.uuid4())
    
    # Create item
    db_item = ClothingItem(
        item_id=item_id,
        title=item.title,
        description=item.description,
        price=item.price,
        category=item.category,
        condition=item.condition,
        brand=item.brand,
        size=item.size,
        color=item.color,
        location=item.location,
        seller_id=user_id,
        image_ids=json.dumps(item.image_ids)
    )
    
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    
    # Get associated images
    images = []
    if item.image_ids:
        db_images = db.query(ImageMetadata).filter(
            ImageMetadata.image_id.in_(item.image_ids)
        ).all()
        
        for img in db_images:
            images.append({
                "image_id": img.image_id,
                "url": f"/uploads/images/{img.file_name}",
                "thumbnail_url": f"/uploads/thumbnails/{img.thumbnail_path}",
                "dimensions": {"width": img.width, "height": img.height}
            })
    
    return ItemResponse(
        id=db_item.id,
        item_id=db_item.item_id,
        title=db_item.title,
        description=db_item.description,
        price=db_item.price,
        category=db_item.category,
        condition=db_item.condition,
        brand=db_item.brand,
        size=db_item.size,
        color=db_item.color,
        location=db_item.location,
        seller_id=db_item.seller_id,
        status=db_item.status,
        views=db_item.views,
        created_at=db_item.created_at,
        images=images
    )

@app.get("/api/items/{item_id}", response_model=ItemResponse)
async def get_item(item_id: str, db: Session = Depends(get_db)):
    """Get a specific item"""
    
    import json
    
    item = db.query(ClothingItem).filter(ClothingItem.item_id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    # Increment views
    item.views += 1
    db.commit()
    
    # Get images
    images = []
    image_ids = json.loads(item.image_ids or "[]")
    if image_ids:
        db_images = db.query(ImageMetadata).filter(
            ImageMetadata.image_id.in_(image_ids)
        ).all()
        
        for img in db_images:
            images.append({
                "image_id": img.image_id,
                "url": f"/uploads/images/{img.file_name}",
                "thumbnail_url": f"/uploads/thumbnails/{img.thumbnail_path}",
                "dimensions": {"width": img.width, "height": img.height}
            })
    
    return ItemResponse(
        id=item.id,
        item_id=item.item_id,
        title=item.title,
        description=item.description,
        price=item.price,
        category=item.category,
        condition=item.condition,
        brand=item.brand,
        size=item.size,
        color=item.color,
        location=item.location,
        seller_id=item.seller_id,
        status=item.status,
        views=item.views,
        created_at=item.created_at,
        images=images
    )

@app.get("/api/items/", response_model=List[ItemResponse])
async def get_items(
    skip: int = 0,
    limit: int = 20,
    category: Optional[str] = None,
    condition: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    db: Session = Depends(get_db)
):
    """Get items with basic filtering"""
    
    import json
    
    query = db.query(ClothingItem).filter(ClothingItem.status == 'active')
    
    if category:
        query = query.filter(ClothingItem.category == category)
    if condition:
        query = query.filter(ClothingItem.condition == condition)
    if min_price is not None:
        query = query.filter(ClothingItem.price >= min_price)
    if max_price is not None:
        query = query.filter(ClothingItem.price <= max_price)
    
    items = query.offset(skip).limit(limit).all()
    
    result = []
    for item in items:
        # Get first image as thumbnail
        images = []
        image_ids = json.loads(item.image_ids or "[]")
        if image_ids:
            db_image = db.query(ImageMetadata).filter(
                ImageMetadata.image_id == image_ids[0]
            ).first()
            if db_image:
                images.append({
                    "image_id": db_image.image_id,
                    "url": f"/uploads/images/{db_image.file_name}",
                    "thumbnail_url": f"/uploads/thumbnails/{db_image.thumbnail_path}",
                    "dimensions": {"width": db_image.width, "height": db_image.height}
                })
        
        result.append(ItemResponse(
            id=item.id,
            item_id=item.item_id,
            title=item.title,
            description=item.description,
            price=item.price,
            category=item.category,
            condition=item.condition,
            brand=item.brand,
            size=item.size,
            color=item.color,
            location=item.location,
            seller_id=item.seller_id,
            status=item.status,
            views=item.views,
            created_at=item.created_at,
            images=images
        ))
    
    return result

@app.get("/health")
async def health_check():
    """Health check"""
    return {"status": "ok", "timestamp": datetime.utcnow()}

# ==================== INITIALIZE DEFAULT DATA ====================

@app.on_event("startup")
async def startup_event():
    """Create default categories"""
    db = SessionLocal()
    try:
        import json
        
        # Check if categories exist
        existing = db.query(ClothingCategory).count()
        if existing == 0:
            # Create default categories
            categories = [
                {"name": "Tops", "subcategories": ["T-Shirts", "Shirts", "Sweaters", "Hoodies"]},
                {"name": "Bottoms", "subcategories": ["Jeans", "Pants", "Shorts", "Skirts"]},
                {"name": "Shoes", "subcategories": ["Sneakers", "Boots", "Sandals", "Heels"]},
                {"name": "Accessories", "subcategories": ["Bags", "Jewelry", "Watches", "Hats"]}
            ]
            
            for cat_data in categories:
                category = ClothingCategory(
                    name=cat_data["name"],
                    subcategories=json.dumps(cat_data["subcategories"])
                )
                db.add(category)
            
            db.commit()
    finally:
        db.close()

# ==================== RUN SERVER ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ==================== USAGE EXAMPLES ====================

"""
# 1. Start the server
uvicorn main:app --reload

# 2. Upload an image
curl -X POST "http://localhost:8000/api/upload/" \
  -F "file=@image.jpg" \
  -F "user_id=user123"

# 3. Create a category
curl -X POST "http://localhost:8000/api/categories/" \
  -H "Content-Type: application/json" \
  -d '{"name": "Dresses", "subcategories": ["Casual", "Formal", "Party"]}'

# 4. Create an item
curl -X POST "http://localhost:8000/api/items/" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Blue Denim Jacket",
    "description": "Vintage blue denim jacket in excellent condition",
    "price": 45.99,
    "category": "Tops",
    "condition": "good",
    "brand": "Levi'\''s",
    "size": "M",
    "color": "Blue",
    "location": "New York",
    "image_ids": ["image-id-from-upload"]
  }' \
  -F "user_id=user123"

# 5. Get items
curl "http://localhost:8000/api/items/?category=Tops&min_price=20&max_price=50"
"""
