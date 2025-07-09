from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from pymongo import MongoClient
from app.auth.auth_handler import get_current_user

router = APIRouter()

client = MongoClient("mongodb://localhost:27017")
db = client["distributed_system"]
users_collection = db["users"]
experts_collection = db["experts"]

# -----------------------
# GET /profile
# -----------------------
@router.get("/profile")
def get_profile(current_user=Depends(get_current_user)):
    role = current_user["role"]
    user_id = current_user["user_id"]

    if role == "user":
        user = users_collection.find_one(
            {"user_id": user_id}, {"_id": 0, "password": 0}
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "role": "user",
            "trust_score": round(user.get("trust_score", 0.5), 2),
            **user
        }

    elif role == "expert":
        expert = experts_collection.find_one(
            {"expert_id": user_id}, {"_id": 0, "password": 0}
        )
        if not expert:
            raise HTTPException(status_code=404, detail="Expert not found")
        return {
            "role": "expert",
            "trust_score": round(expert.get("trust_score", 0.5), 2),
            **expert
        }

    else:
        raise HTTPException(status_code=403, detail="Invalid role")


# -----------------------
# POST /update_profile (Expert only)
# -----------------------
class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    qualifications: Optional[str] = None
    experience_years: Optional[int] = None
    quiz_score: Optional[int] = None
    proof_resume: Optional[str] = None
    portfolio_url: Optional[str] = None
    expert_tags: Optional[list[str]] = None

@router.post("/update_profile")
def update_profile(data: UpdateProfileRequest, current_user=Depends(get_current_user)):
    if current_user["role"] != "expert":
        raise HTTPException(status_code=403, detail="Only experts can update their profile.")

    expert_id = current_user["user_id"]

    # Collect only non-null fields to update
    update_fields = {field: value for field, value in data.dict().items() if value is not None}

    if not update_fields:
        raise HTTPException(status_code=400, detail="No updates provided.")

    result = experts_collection.update_one(
        {"expert_id": expert_id},
        {"$set": update_fields}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Profile not updated.")

    return {"message": "Profile updated successfully."}
