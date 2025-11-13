"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List

class Seller(BaseModel):
    name: str = Field(..., description="Seller display name")
    email: str = Field(..., description="Seller contact email")
    avatar_url: Optional[str] = Field(None, description="Avatar image URL")

class Product(BaseModel):
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: Optional[str] = Field(None, description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")
    seller_id: str = Field(..., description="Owner seller id")
    image_url: Optional[str] = Field(None, description="Product image URL")

class Stream(BaseModel):
    seller_id: str = Field(..., description="Seller running the stream")
    product_ids: List[str] = Field(default_factory=list, description="Products featured in stream")
    discount_percent: float = Field(..., ge=0, le=100, description="Discount percent active during stream")
    duration_seconds: int = Field(..., ge=10, le=36000, description="Duration of the live discount window in seconds")
    active: bool = Field(True, description="Whether stream is currently live")
    start_time: Optional[str] = Field(None, description="ISO time the stream started")
    end_time: Optional[str] = Field(None, description="ISO time the stream ends")
    title: Optional[str] = Field(None, description="Optional stream title")

class Order(BaseModel):
    buyer_name: str = Field(...)
    buyer_email: str = Field(...)
    product_id: str = Field(...)
    quantity: int = Field(1, ge=1)
    seller_id: str = Field(...)
    unit_price: float = Field(..., ge=0)
    discount_percent: float = Field(0, ge=0, le=100)
    total_price: float = Field(..., ge=0)
    stream_id: Optional[str] = Field(None)
