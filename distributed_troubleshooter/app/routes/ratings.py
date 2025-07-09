from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
from pymongo import MongoClient
from app.auth.auth_handler import get_current_user

router = APIRouter()

client = MongoClient("mongodb://localhost:27017")
db = client["distributed_system"]
ratings_collection = db["ratings"]
users_collection = db["users"]
experts_collection = db["experts"]

# 📦 Rating Schema
class Rating(BaseModel):
    issue_id: str
    recipient_id: str
    recipient_role: str  # "user" or "expert"
    stars: int           # 1 to 5
    comment: str

@router.post("/submit_rating")
def submit_rating(rating: Rating, current_user=Depends(get_current_user)):
    if rating.stars < 1 or rating.stars > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5.")

    # ✅ Prevent duplicate ratings for same issue
    existing = ratings_collection.find_one({
        "issue_id": rating.issue_id,
        "rated_by": current_user["user_id"],
        "recipient_id": rating.recipient_id
    })
    if existing:
        raise HTTPException(status_code=400, detail="You have already rated this user for this issue.")

    # ✅ Save new rating
    rating_doc = {
        "issue_id": rating.issue_id,
        "rated_by": current_user["user_id"],
        "rated_by_role": current_user["role"],
        "recipient_id": rating.recipient_id,
        "recipient_role": rating.recipient_role,
        "stars": rating.stars,
        "comment": rating.comment,
        "timestamp": datetime.utcnow()
    }
    ratings_collection.insert_one(rating_doc)

    # ✅ Update average trust score of recipient
    all_ratings = ratings_collection.find({ "recipient_id": rating.recipient_id })
    total = 0
    count = 0
    for r in all_ratings:
        total += r["stars"]
        count += 1
    avg_score = round(total / count, 2)

    # Save back to user/expert collection
    if rating.recipient_role == "expert":
        experts_collection.update_one(
            { "expert_id": rating.recipient_id },
            { "$set": { "trust_score": avg_score } }
        )
    elif rating.recipient_role == "user":
        users_collection.update_one(
            { "user_id": rating.recipient_id },
            { "$set": { "trust_score": avg_score } }
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid recipient role.")

    return {
        "message": "Rating submitted successfully.",
        "new_trust_score": avg_score
    }
