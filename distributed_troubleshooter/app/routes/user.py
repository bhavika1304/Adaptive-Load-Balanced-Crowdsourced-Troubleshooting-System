from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
from pymongo import MongoClient
from app.auth.auth_handler import get_current_user
from app.services.utils import match_best_expert, retry_assignment
import uuid
from app.websocket_manager import ws_manager  # ✅ correct if 'websocket_manager.py' is inside the app/ folder
from app.services.utils import get_best_region
import asyncio
from fastapi import BackgroundTasks

router = APIRouter()

client = MongoClient("mongodb://localhost:27017")
db = client["distributed_system"]
issues_collection = db["issues"]
experts_collection = db["experts"]
messages_collection = db["messages"]  # ✅ Needed to insert system message

class IssueCreate(BaseModel):
    title: str
    description: str
    category: str
    urgency: int  # 1 to 5

@router.post("/report_issue")
async def report_issue(data: IssueCreate, background_tasks: BackgroundTasks, current_user=Depends(get_current_user)):
    if current_user["role"] != "user":
        raise HTTPException(status_code=403, detail="Only users can report issues.")

    user_region = current_user.get("region") or "north"
    if not user_region:
        raise HTTPException(status_code=400, detail="User region not set. Please update your profile.")

    # Step 1: Check for available experts in user's region
    experts_in_user_region = list(experts_collection.find({
        "region": user_region,
        "is_verified": True,
        "is_available": True
    }))

    if experts_in_user_region:
        chosen_region = user_region
        filtered_experts = experts_in_user_region
    else:
        # Step 2: Fallback to least-loaded region
        chosen_region = get_best_region()
        filtered_experts = list(experts_collection.find({
            "region": chosen_region,
            "is_verified": True,
            "is_available": True
        }))

    issue_id = str(uuid.uuid4())

    issue = {
        "issue_id": issue_id,
        "title": data.title,
        "description": data.description,
        "category": data.category,
        "urgency": data.urgency,
        "status": "pending",
        "timestamp": datetime.utcnow(),
        "assigned_expert": None,
        "submitted_by": current_user["user_id"],
        "reassignment_log": [],
        "region": chosen_region,
        "done_by_user": False,
        "done_by_expert": False
    }

    if not issues_collection.insert_one(issue).inserted_id:
        raise HTTPException(status_code=500, detail="Issue not saved.")

    messages_collection.insert_one({
        "issue_id": issue_id,
        "sender_id": None,
        "sender_role": "system",
        "content": "Issue created.",
        "timestamp": datetime.utcnow()
    })

    await ws_manager.send_event(current_user["user_id"], "issue_created", {"issue_id": issue_id})

    if not filtered_experts:
        return {"message": "Issue submitted, but no available experts in any region.", "issue_id": issue_id}

    best_expert_id = match_best_expert(issue, filtered_experts)

    if not best_expert_id:
        background_tasks.add_task(retry_assignment, issue_id)
        await ws_manager.send_event(current_user["user_id"], "no_expert_now", {"issue_id": issue_id})
        return {"message": "Issue submitted, retrying shortly.", "issue_id": issue_id}

    # Assign the expert
    issues_collection.update_one(
        {"issue_id": issue_id},
        {"$set": {"assigned_expert": best_expert_id, "status": "assigned"}}
    )

    experts_collection.update_one(
        {"expert_id": best_expert_id},
        {"$inc": {"active_issues": 1}}
    )

    await ws_manager.send_event(best_expert_id, "issue_assigned", {"message": "A new issue has been assigned to you."})

    return {
        "message": "Issue submitted and expert assigned successfully.",
        "issue_id": issue_id,
        "assigned_expert": best_expert_id
    }


# -------------------------------
# ✅ GET /my_issues
# -------------------------------
@router.get("/my_issues")
def get_my_issues(current_user=Depends(get_current_user)):
    user_id = current_user["user_id"]
    issues = list(issues_collection.find({"submitted_by": user_id}))

    for issue in issues:
        issue["_id"] = str(issue["_id"])
        expert_id = issue.get("assigned_expert")
        issue["assigned_expert_id"] = expert_id  # ✅ ADD THIS LINE

        # Optional: convert expert_id to email if needed
        if expert_id:
            expert = experts_collection.find_one({"expert_id": expert_id})
            issue["assigned_expert"] = expert.get("email", expert_id) if expert else expert_id
        else:
            issue["assigned_expert"] = "Not Assigned"

    return issues

# -------------------------------
# ✅ DELETE /delete_issue/{issue_id}
# -------------------------------
@router.delete("/delete_issue/{issue_id}")
async def delete_issue(issue_id: str, current_user=Depends(get_current_user)):
    issue = issues_collection.find_one({"issue_id": issue_id})
    if not issue or issue["submitted_by"] != current_user["user_id"]:
        raise HTTPException(status_code=404, detail="Issue not found or unauthorized.")

    #if issue["status"] != "pending":
        #raise HTTPException(status_code=400, detail="Only pending issues can be deleted.")

    issues_collection.delete_one({"issue_id": issue_id})

    # ✅ Notify user via WebSocket
    await ws_manager.send_event(current_user["user_id"], "issue_deleted", {"message": "Your issue was deleted."})

    return {"message": "Issue deleted successfully."}

@router.post("/escalate_issue/{issue_id}")
async def escalate_issue(issue_id: str, current_user=Depends(get_current_user)):
    if current_user["role"] != "user":
        raise HTTPException(status_code=403, detail="Only users can escalate issues.")

    issue = issues_collection.find_one({"issue_id": issue_id})
    if not issue or issue.get("submitted_by") != current_user["user_id"]:
        raise HTTPException(status_code=404, detail="Issue not found or unauthorized.")

    old_expert_id = issue.get("assigned_expert")
    if not old_expert_id:
        return {"message": "No expert currently assigned to escalate from."}

    # ✅ Add old expert to skipped_by
    issues_collection.update_one(
        {"issue_id": issue_id},
        {
            "$addToSet": {"skipped_by": old_expert_id},
            "$set": {"assigned_expert": None, "status": "pending"}
        }
    )

    # ✅ Decrease load of skipped expert
    experts_collection.update_one(
        {"expert_id": old_expert_id},
        {"$inc": {"active_issues": -1}}
    )

    # ✅ Fetch updated issue and all valid fallback experts
    updated_issue = issues_collection.find_one({"issue_id": issue_id})
    skip_list = list(set(updated_issue.get("rejected_by", []) + updated_issue.get("skipped_by", [])))

    fallback_experts = list(experts_collection.find({
        "is_available": True,
        "is_verified": True,
        "expert_id": {"$nin": skip_list}
    }))

    new_expert_id = match_best_expert(updated_issue, fallback_experts)

    if new_expert_id:
        issues_collection.update_one(
            {"issue_id": issue_id},
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

        # ✅ Notify both experts and user
        await ws_manager.send_event(new_expert_id, "issue_assigned", {"issue_id": issue_id})
        await ws_manager.send_event(current_user["user_id"], "issue_assigned", {
            "issue_id": issue_id,
            "message": "Your issue has been reassigned to another expert."
        })
        await ws_manager.send_event(old_expert_id, "issue_unassigned", {
            "issue_id": issue_id,
            "message": "You have been removed from an escalated issue."
        })

        return {"message": "Issue escalated and reassigned.", "new_expert": new_expert_id}

    await ws_manager.send_event(current_user["user_id"], "no_expert_now", {"issue_id": issue_id})
    return {"message": "No fallback expert available currently."}