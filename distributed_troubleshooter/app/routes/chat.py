from fastapi import APIRouter, HTTPException, Depends, Request
from pymongo import MongoClient
from datetime import datetime
from app.auth.auth_handler import get_current_user
from app.websocket_manager import ws_manager  # ✅ WebSocket handler

router = APIRouter()

client = MongoClient("mongodb://localhost:27017")
db = client["distributed_system"]
messages_collection = db["messages"]
issues_collection = db["issues"]

# -------------------------------
# 📨 Send a New Message
# -------------------------------
@router.post("/messages/{issue_id}")
async def send_message(issue_id: str, request: Request, current_user=Depends(get_current_user)):
    issue = issues_collection.find_one({"issue_id": issue_id})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    user_id = current_user["user_id"]
    role = current_user["role"]

    if role == "user" and issue.get("submitted_by") != user_id:
        raise HTTPException(status_code=403, detail="You are not part of this issue")
    if role == "expert" and issue.get("assigned_expert") != user_id:
        raise HTTPException(status_code=403, detail="You are not part of this issue")

    body = await request.json()
    content = body.get("message")
    if not content:
        raise HTTPException(status_code=400, detail="Message content missing")

    message_doc = {
        "issue_id": issue_id,
        "sender_id": user_id,
        "sender_role": role,
        "content": content,
        "timestamp": datetime.utcnow()
    }

    messages_collection.insert_one(message_doc)

    recipient_id = issue["assigned_expert"] if role == "user" else issue["submitted_by"]
    await ws_manager.send_event(recipient_id, "new_message", {
        "message": "new message sent",
        "issue_id": issue_id
    })

    return {"message": "Message sent"}


# -------------------------------
# 📄 Get Messages (return list even if issue not found)
# -------------------------------
@router.get("/messages/{issue_id}")
def get_messages(issue_id: str, current_user=Depends(get_current_user)):
    issue = issues_collection.find_one({"issue_id": issue_id})

    # ✅ Always return an array (empty if issue not found)
    if not issue:
        return []

    user_id = current_user["user_id"]
    role = current_user["role"]

    if role == "user" and issue.get("submitted_by") != user_id:
        raise HTTPException(status_code=403, detail="You are not part of this issue")
    if role == "expert" and issue.get("assigned_expert") != user_id:
        raise HTTPException(status_code=403, detail="You are not part of this issue")

    messages = list(messages_collection.find({"issue_id": issue_id}).sort("timestamp", 1))
    for msg in messages:
        msg["_id"] = str(msg["_id"])
        msg["timestamp"] = msg["timestamp"].isoformat()

    return messages

# -------------------------------
# ✅ Mark Issue as Done
# -------------------------------
@router.post("/mark_done/{issue_id}")
async def mark_issue_done(issue_id: str, current_user=Depends(get_current_user)):
    issue = issues_collection.find_one({"issue_id": issue_id})
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    role = current_user["role"]
    user_id = current_user["user_id"]

    if role == "user":
        if issue.get("submitted_by") != user_id:
            raise HTTPException(status_code=403, detail="You are not part of this issue")
        issues_collection.update_one({"issue_id": issue_id}, {"$set": {"done_by_user": True}})
    elif role == "expert":
        if issue.get("assigned_expert") != user_id:
            raise HTTPException(status_code=403, detail="You are not part of this issue")
        issues_collection.update_one({"issue_id": issue_id}, {"$set": {"done_by_expert": True}})
    else:
        raise HTTPException(status_code=403, detail="Invalid role")

    updated = issues_collection.find_one({"issue_id": issue_id})
    if updated.get("done_by_user") and updated.get("done_by_expert"):
        issues_collection.update_one({"issue_id": issue_id}, {"$set": {"status": "closed"}})

        await ws_manager.send_event(updated["submitted_by"], "issue_closed", {"issue_id": issue_id})
        await ws_manager.send_event(updated["assigned_expert"], "issue_closed", {"issue_id": issue_id})

        return {
            "status": "closed",
            "message": "Issue fully marked as done and closed.",
            "request_feedback": True
        }

    return {
        "status": "pending_other_party",
        "message": "Marked done. Awaiting other party.",
        "request_feedback": False
    }
