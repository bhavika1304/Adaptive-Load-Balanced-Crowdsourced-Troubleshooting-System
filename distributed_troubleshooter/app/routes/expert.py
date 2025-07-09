import asyncio

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from pymongo import MongoClient
from datetime import datetime
from app.auth.auth_handler import get_current_user
from app.websocket_manager import ws_manager  # ✅ correct if 'websocket_manager.py' is inside the app/ folder
from app.services.utils import match_best_expert, retry_assignment
from fastapi import BackgroundTasks
router = APIRouter()

client = MongoClient("mongodb://localhost:27017")
db = client["distributed_system"]
issues_collection = db["issues"]
experts_collection = db["experts"]
feedback_collection = db["feedback"]
user_feedback_collection = db["user_feedback"]
users_collection = db["users"]

# -----------------------
# GET /expert_assignments
# -----------------------
@router.get("/expert_assignments")
def get_assignments(current_user=Depends(get_current_user)):
    if current_user["role"] != "expert":
        raise HTTPException(status_code=403, detail="Only experts can view their assignments.")

    expert_id = current_user["user_id"]
    assignments = list(issues_collection.find({
        "assigned_expert": expert_id,
        "status": {"$in": ["assigned", "in_progress", "awaiting_user_confirmation"]}
    }))
    for a in assignments:
        a["_id"] = str(a["_id"])
        user = users_collection.find_one({"user_id": a["submitted_by"]})
        a["submitted_by_id"] = a["submitted_by"]  # Add this line
        a["submitted_by"] = user.get("email", a["submitted_by"]) if user else a["submitted_by"]
    return assignments


# -----------------------
# POST /accept_assignment
# -----------------------
class AcceptRequest(BaseModel):
    issue_id: str

@router.post("/accept_assignment")
async def accept_assignment(data: AcceptRequest, current_user=Depends(get_current_user)):
    if current_user["role"] != "expert":
        raise HTTPException(status_code=403, detail="Only experts can accept assignments.")

    expert_id = current_user["user_id"]
    issue = issues_collection.find_one({"issue_id": data.issue_id, "assigned_expert": expert_id})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found or not assigned to this expert.")

    issues_collection.update_one(
        {"issue_id": data.issue_id},
        {"$set": {"status": "in_progress"}}
    )
    await ws_manager.send_event(issue["submitted_by"], "issue_started", {"issue_id": issue["issue_id"]})
    return {"message": "Assignment accepted."}

# -----------------------
# POST /submit_resolution
# -----------------------
class ResolutionRequest(BaseModel):
    issue_id: str
    resolution_notes: str

@router.post("/submit_resolution")
async def submit_resolution(data: ResolutionRequest, current_user=Depends(get_current_user)):
    if current_user["role"] != "expert":
        raise HTTPException(status_code=403, detail="Only experts can submit resolutions.")

    expert_id = current_user["user_id"]
    issue = issues_collection.find_one({"issue_id": data.issue_id, "assigned_expert": expert_id})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found or not assigned to expert.")

    issues_collection.update_one(
        {"issue_id": data.issue_id},
        {
            "$set": {
                "status": "awaiting_user_confirmation",
                "resolution_notes": data.resolution_notes,
                "resolved_at": datetime.utcnow(),
                "done_by_user": False,
                "done_by_expert": False
            }
        }
    )

    experts_collection.update_one(
        {"expert_id": expert_id},
        {"$inc": {"active_issues": -1}}
    )

    await asyncio.sleep(0.1)
    await ws_manager.send_event(
        issue["submitted_by"],
        "resolution_submitted",
        {"issue_id": data.issue_id, "resolution_notes": data.resolution_notes}  # ✅ Include resolution_notes
    )

    return {"message": "Resolution submitted. Awaiting user's confirmation."}

# -----------------------
# POST /rate_expert
# -----------------------
class RatingRequest(BaseModel):
    issue_id: str
    expert_id: str
    rating: int
    comment: str = ""

@router.post("/rate_expert")
async def rate_expert(data: RatingRequest, current_user=Depends(get_current_user)):
    if current_user["role"] != "user":
        raise HTTPException(status_code=403, detail="Only users can rate experts.")

    feedback = {
        "issue_id": data.issue_id,
        "expert_id": data.expert_id,
        "rating": data.rating,
        "comment": data.comment,
        "submitted_at": datetime.utcnow()
    }
    feedback_collection.insert_one(feedback)

    expert = experts_collection.find_one({"expert_id": data.expert_id})
    if not expert:
        raise HTTPException(status_code=404, detail="Expert not found.")

    current_score = expert.get("trust_score", 0.5)
    vote_count = expert.get("trust_votes", 0)
    normalized_rating = data.rating / 5
    new_score = round(((current_score * vote_count) + normalized_rating) / (vote_count + 1), 2)
    experts_collection.update_one(
        {"expert_id": data.expert_id},
        {"$set": {"trust_score": new_score}, "$inc": {"trust_votes": 1}}
    )

    await ws_manager.send_event(data.expert_id, "expert_rated", {"issue_id": data.issue_id})
    return {"message": "Feedback recorded. Trust score updated."}

# -----------------------
# POST /rate_user
# -----------------------
class UserRatingRequest(BaseModel):
    issue_id: str
    user_id: str
    rating: int
    comment: str = ""

@router.post("/rate_user")
async def rate_user(data: UserRatingRequest, current_user=Depends(get_current_user)):
    if current_user["role"] != "expert":
        raise HTTPException(status_code=403, detail="Only experts can rate users.")

    feedback = {
        "issue_id": data.issue_id,
        "user_id": data.user_id,
        "expert_id": current_user["user_id"],
        "rating": data.rating,
        "comment": data.comment,
        "submitted_at": datetime.utcnow()
    }
    user_feedback_collection.insert_one(feedback)

    user = users_collection.find_one({"user_id": data.user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    current_score = user.get("trust_score", 0.5)
    vote_count = user.get("trust_votes", 1)
    normalized_rating = data.rating / 5  # Convert 1–5 to 0–1

    new_score = round(((current_score * vote_count) + normalized_rating) / (vote_count + 1), 2)

    users_collection.update_one(
        {"user_id": data.user_id},
        {"$set": {"trust_score": new_score}, "$inc": {"trust_votes": 1}}
    )

    await ws_manager.send_event(data.user_id, "user_rated", {"issue_id": data.issue_id})
    return {"message": "User feedback recorded. User trust score updated."}

@router.get("/experts_unverified")
def get_unverified_experts(current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this.")

    experts = list(experts_collection.find({"is_verified": False}))
    for e in experts:
        e["_id"] = str(e["_id"])
    return experts

@router.post("/admin/verify_expert/{expert_id}")
def verify_expert(expert_id: str, notes: str = "", current_user=Depends(get_current_user)):
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
                "verification_notes": notes or "Verified by admin"
            }
        }
    )

    return {"message": f"Expert {expert_id} verified."}

# -----------------------
# POST /submit_quiz_score
# -----------------------
class QuizScoreRequest(BaseModel):
    score: int

@router.post("/submit_quiz_score")
def submit_quiz_score(data: QuizScoreRequest, current_user=Depends(get_current_user)):
    if current_user["role"] != "expert":
        raise HTTPException(status_code=403, detail="Only experts can submit quiz scores.")

    expert_id = current_user["user_id"]
    result = experts_collection.update_one(
        {"expert_id": expert_id},
        {"$set": {"quiz_score": data.score}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Expert not found.")

    return {"message": "Quiz score submitted successfully."}

# -----------------------
# POST /update_availability
# -----------------------
class AvailabilityRequest(BaseModel):
    availability: str  # should be either 'available' or 'busy'

@router.post("/update_availability")
def update_availability(data: AvailabilityRequest, current_user=Depends(get_current_user)):
    if current_user["role"] != "expert":
        raise HTTPException(status_code=403, detail="Only experts can update availability.")

    if data.availability not in ["available", "busy"]:
        raise HTTPException(status_code=400, detail="Invalid availability value.")

    expert_id = current_user["user_id"]
    is_available = data.availability == "available"
    result = experts_collection.update_one(
        {"expert_id": expert_id},
        {"$set": {"is_available": is_available}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Expert not found.")

    return {"message": f"Availability updated to '{data.availability}'."}

@router.post("/mark_done/{issue_id}")
async def mark_done(issue_id: str, current_user=Depends(get_current_user)):
    issue = issues_collection.find_one({"issue_id": issue_id})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    role = current_user["role"]
    updates = {}

    if role == "user":
        updates["done_by_user"] = True
    elif role == "expert":
        updates["done_by_expert"] = True
    else:
        raise HTTPException(status_code=403, detail="Invalid role")

    issues_collection.update_one({"issue_id": issue_id}, {"$set": updates})
    updated = issues_collection.find_one({"issue_id": issue_id})

    if updated.get("done_by_user") and updated.get("done_by_expert"):
        issues_collection.update_one(
            {"issue_id": issue_id},
            {"$set": {"status": "closed"}}
        )
        await ws_manager.send_event(updated["submitted_by"], "issue_closed", {"issue_id": issue_id})
        await ws_manager.send_event(updated["assigned_expert"], "issue_closed", {"issue_id": issue_id})
        return {"status": "closed", "message": "Issue successfully closed."}
    else:
        return {"status": "pending", "message": "Marked done. Awaiting confirmation from other party."}

class RejectRequest(BaseModel):
    issue_id: str

@router.post("/reject_issue")
async def reject_issue(data: RejectRequest, current_user=Depends(get_current_user)):
    if current_user["role"] != "expert":
        raise HTTPException(status_code=403, detail="Only experts can reject issues.")

    issue = issues_collection.find_one({"issue_id": data.issue_id})
    if not issue or issue.get("assigned_expert") != current_user["user_id"]:
        raise HTTPException(status_code=404, detail="Issue not found or not assigned to you.")

    # Step 1: Unassign and add to rejection list
    issues_collection.update_one(
        {"issue_id": data.issue_id},
        {
            "$set": {"assigned_expert": None, "status": "pending"},
            "$addToSet": {"rejected_by": current_user["user_id"]}
        }
    )

    # ✅ Decrease active_issues count for rejecting expert
    experts_collection.update_one(
        {"expert_id": current_user["user_id"]},
        {"$inc": {"active_issues": -1}}
    )

    # Step 2: Fetch updated issue and get all other available experts
    issue = issues_collection.find_one({"issue_id": data.issue_id})
    rejected_ids = issue.get("rejected_by", [])

    available_experts = list(experts_collection.find({
        "is_verified": True,
        "availability": "available",
        "expert_id": {"$nin": rejected_ids}
    }))

    # Step 3: Match best expert
    new_expert_id = match_best_expert(issue, available_experts)

    if new_expert_id:
        # ✅ Reassign and log it
        issues_collection.update_one(
            {"issue_id": data.issue_id},
            {
                "$set": {"assigned_expert": new_expert_id, "status": "assigned"},
                "$push": {
                    "reassignment_log": {
                        "expert_id": new_expert_id,
                        "timestamp": datetime.utcnow()
                    }
                }
            }
        )
        experts_collection.update_one({"expert_id": new_expert_id}, {"$inc": {"active_issues": 1}})

        # ✅ Notify expert and user
        await ws_manager.send_event(new_expert_id, "issue_assigned", {"issue_id": data.issue_id})

        # ❌ No other expert found → mark for retry
        issues_collection.update_one(
            {"issue_id": data.issue_id},
            {"$set": {"reassignment_status": "waiting"}}
        )

        if issue.get("submitted_by"):
            await ws_manager.send_event(issue["submitted_by"], "issue_assigned", {
                "issue_id": data.issue_id,
                "message": "Your issue is currently unassigned. We are retrying periodically to find a suitable expert."
            })

        return {"message": "Issue unassigned. No other expert available currently."}

    # ❌ No other expert found
    if issue.get("submitted_by"):
        await ws_manager.send_event(issue["submitted_by"], "issue_assigned", {
            "issue_id": data.issue_id,
            "message": "Your issue is currently unassigned. We're trying to find another expert."
        })

    return {"message": "Issue unassigned. No other expert available currently."}
# Background retry assignment
    asyncio.create_task(retry_assignment(data.issue_id))
