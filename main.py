import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Seller, Product, Stream, Order

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utility to convert Mongo docs

def serialize(doc):
    if not doc:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    # Convert datetime to iso
    for k, v in list(doc.items()):
        if hasattr(v, 'isoformat'):
            doc[k] = v.isoformat()
    return doc

@app.get("/")
def read_root():
    return {"message": "Live Commerce API ready"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Connected & Working"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response

# Sellers
class SellerIn(Seller):
    pass

@app.post("/api/sellers")
def create_seller(payload: SellerIn):
    seller_id = create_document("seller", payload)
    return {"id": seller_id}

@app.get("/api/sellers")
def list_sellers():
    docs = get_documents("seller")
    return [serialize(d) for d in docs]

# Products
class ProductIn(Product):
    pass

@app.post("/api/products")
def create_product(payload: ProductIn):
    # Basic check the seller exists
    if not db["seller"].find_one({"_id": ObjectId(payload.seller_id)}):
        raise HTTPException(status_code=400, detail="Seller not found")
    product_id = create_document("product", payload)
    return {"id": product_id}

@app.get("/api/products")
def list_products(seller_id: Optional[str] = None):
    q = {}
    if seller_id:
        q["seller_id"] = seller_id
    docs = get_documents("product", q)
    return [serialize(d) for d in docs]

# Streams
class StreamIn(Stream):
    pass

@app.post("/api/streams")
def create_stream(payload: StreamIn):
    # Validate seller
    if not db["seller"].find_one({"_id": ObjectId(payload.seller_id)}):
        raise HTTPException(status_code=400, detail="Seller not found")
    # Validate products belong to seller
    if payload.product_ids:
        cnt = db["product"].count_documents({
            "_id": {"$in": [ObjectId(pid) for pid in payload.product_ids]},
            "seller_id": payload.seller_id
        })
        if cnt != len(payload.product_ids):
            raise HTTPException(status_code=400, detail="Invalid products for seller")

    now = datetime.now(timezone.utc)
    start = now
    end = now + timedelta(seconds=payload.duration_seconds)
    data = payload.model_dump()
    data.update({
        "active": True,
        "start_time": start,
        "end_time": end
    })
    stream_id = create_document("stream", data)
    return {"id": stream_id, "start_time": start.isoformat(), "end_time": end.isoformat()}

@app.get("/api/streams")
def list_streams(active: Optional[bool] = None):
    q = {}
    if active is not None:
        q["active"] = active
    docs = get_documents("stream", q)
    # Auto-expire streams
    out = []
    now = datetime.now(timezone.utc)
    for d in docs:
        if d.get("end_time") and isinstance(d["end_time"], datetime) and d["end_time"] < now and d.get("active"):
            db["stream"].update_one({"_id": d["_id"]}, {"$set": {"active": False}})
            d["active"] = False
        out.append(serialize(d))
    return out

@app.get("/api/streams/{stream_id}")
def get_stream(stream_id: str):
    d = db["stream"].find_one({"_id": ObjectId(stream_id)})
    if not d:
        raise HTTPException(status_code=404, detail="Stream not found")
    # update active if expired
    now = datetime.now(timezone.utc)
    if d.get("end_time") and isinstance(d["end_time"], datetime) and d["end_time"] < now and d.get("active"):
        db["stream"].update_one({"_id": d["_id"]}, {"$set": {"active": False}})
        d["active"] = False
    return serialize(d)

# Orders
class OrderIn(BaseModel):
    buyer_name: str
    buyer_email: str
    product_id: str
    quantity: int = 1
    stream_id: Optional[str] = None

@app.post("/api/orders")
def create_order(payload: OrderIn):
    product = db["product"].find_one({"_id": ObjectId(payload.product_id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    seller_id = product.get("seller_id")

    unit_price = float(product.get("price", 0))
    discount_percent = 0.0

    # If stream id given, verify it is active and includes this product
    if payload.stream_id:
        stream = db["stream"].find_one({"_id": ObjectId(payload.stream_id)})
        if not stream:
            raise HTTPException(status_code=404, detail="Stream not found")
        now = datetime.now(timezone.utc)
        # Check active and within time window
        end_time = stream.get("end_time")
        if end_time and isinstance(end_time, datetime) and end_time < now:
            # expire
            db["stream"].update_one({"_id": stream["_id"]}, {"$set": {"active": False}})
            raise HTTPException(status_code=400, detail="Stream discount window ended")
        if not stream.get("active"):
            raise HTTPException(status_code=400, detail="Stream not active")
        if str(product["_id"]) not in [str(pid) for pid in stream.get("product_ids", [])]:
            raise HTTPException(status_code=400, detail="Product not in stream")
        discount_percent = float(stream.get("discount_percent", 0))

    total_price = round(unit_price * payload.quantity * (1 - discount_percent/100), 2)

    order_doc = {
        "buyer_name": payload.buyer_name,
        "buyer_email": payload.buyer_email,
        "product_id": payload.product_id,
        "quantity": payload.quantity,
        "seller_id": seller_id,
        "unit_price": unit_price,
        "discount_percent": discount_percent,
        "total_price": total_price,
        "stream_id": payload.stream_id,
        "status": "confirmed",
    }

    order_id = create_document("order", order_doc)
    return {"id": order_id, "total_price": total_price}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
