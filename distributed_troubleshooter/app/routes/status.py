from fastapi import APIRouter, HTTPException, Depends
from pymongo import MongoClient
from app.auth.auth_handler import get_current_user
from datetime import datetime

router = APIRouter()
client = MongoClient("mongodb://localhost:27017")
db = client["distributed_system"]
issues_collection = db["issues"]

@router.post("/mark_done/{issue_id}")
async def mark_done(issue_id: str, current_user=Depends(get_current_user)):
    issue = issues_collection.find_one({"issue_id": issue_id})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    role = current_user["role"]
    user_id = current_user["user_id"]

    updates = {}
    if role == "expert" and issue.get("assigned_expert") == user_id:
        updates["done_by_expert"] = True
    elif role == "user" and issue.get("submitted_by") == user_id:
        updates["done_by_user"] = True
    else:
        raise HTTPException(status_code=403, detail="You are not authorized for this action.")

    issues_collection.update_one({"issue_id": issue_id}, {"$set": updates})

    updated = issues_collection.find_one({"issue_id": issue_id})
    if updated.get("done_by_user") and updated.get("done_by_expert"):
        issues_collection.update_one({"issue_id": issue_id}, {"$set": {"status": "closed", "closed_at": datetime.utcnow()}})

        # ✅ Trigger feedback on both sides
        from app.websocket_manager import ws_manager  # safe to import here

        await ws_manager.send_event(updated["submitted_by"], "issue_closed", {
            "issue_id": issue_id,
            "trigger_rating": True,
            "recipient_id": updated["assigned_expert"]
        })

        await ws_manager.send_event(updated["assigned_expert"], "issue_closed", {
            "issue_id": issue_id,
            "trigger_rating": True,
            "recipient_id": updated["submitted_by"]
        })

        return {"message": "Issue fully closed.", "status": "closed"}

    return {"message": "Marked as done. Waiting for the other party.", "status": "pending"}
