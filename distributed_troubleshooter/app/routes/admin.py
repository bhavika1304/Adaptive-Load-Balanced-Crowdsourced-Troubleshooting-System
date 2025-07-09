from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from pymongo import MongoClient
from app.auth.auth_handler import get_current_user

router = APIRouter()

client = MongoClient("mongodb://localhost:27017")
db = client["distributed_system"]
issues_collection = db["issues"]
experts_collection = db["experts"]

# -----------------------
# Pydantic model for tag update
# -----------------------
class TagUpdateRequest(BaseModel):
    tags: list[str]
    notes: str = ""

# -----------------------
# POST /admin/login
# -----------------------
@router.post("/admin/login")
def admin_login(payload: dict):
    if payload.get("username") == "admin" and payload.get("password") == "admin123":
        return {"token": "admin-token"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

# -----------------------
# GET /experts_unverified
# -----------------------
@router.get("/experts_unverified")
def get_unverified_experts(current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this.")
    experts = list(experts_collection.find({"is_verified": False}))
    for e in experts:
        e["_id"] = str(e["_id"])  # Convert ObjectId
    return experts

# -----------------------
# POST /admin/verify_expert/{expert_id}
# -----------------------
@router.post("/admin/verify_expert/{expert_id}")
def verify_expert(expert_id: str, payload: TagUpdateRequest, current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can verify experts.")

    expert = experts_collection.find_one({"expert_id": expert_id})
    if not expert:
        raise HTTPException(status_code=404, detail="Expert not found.")

    if expert.get("is_verified", False):
        return {"message": "Expert already verified."}

    experts_collection.update_one(
        {"expert_id": expert_id},
        {
            "$set": {
                "is_verified": True,
                "verification_notes": payload.notes or "Verified by admin",
                "expert_tags": payload.tags
            }
        }
    )

    return {"message": f"Expert {expert_id} verified and tagged."}

# -----------------------
# GET /region_stats
# -----------------------
@router.get("/region_stats")
def get_region_stats():
    regions = ["north", "south", "east", "west"]
    stats = {}

    for region in regions:
        active_issues = issues_collection.count_documents({
            "region": region,
            "status": {"$in": ["pending", "assigned", "in_progress"]}
        })

        available_experts = experts_collection.count_documents({
            "region": region,
            "is_available": True,
            "is_verified": True
        })

        stats[region] = {
            "active_issues": active_issues,
            "available_experts": available_experts
        }

    return stats

# -----------------------
# GET /all_issues_by_region
# -----------------------
@router.get("/all_issues_by_region")
def get_issues_by_region(current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this.")

    grouped = {"north": [], "south": [], "east": [], "west": []}
    issues = list(issues_collection.find())

    for issue in issues:
        region = issue.get("region", "unknown")
        issue["_id"] = str(issue["_id"])
        issue["assigned_expert"] = issue.get("assigned_expert", "Not Assigned")
        grouped.setdefault(region, []).append(issue)

    return grouped

@router.get("/rerouted_issues")
def get_rerouted_issues(current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view this.")

    issues = list(issues_collection.find(
        {"reassignment_log.1": {"$exists": True}},
        {
            "_id": 0,
            "issue_id": 1,
            "title": 1,
            "region": 1,
            "reassignment_log": 1
        }
    ))

    return issues
