import asyncio
import re
from difflib import SequenceMatcher
from sentence_transformers import SentenceTransformer, util
from pymongo import MongoClient

from app.websocket_manager import ws_manager

# Load the sentence embedding model once (cache)
MODEL = SentenceTransformer('all-MiniLM-L6-v2')

# MongoDB connection for region scoring
client = MongoClient("mongodb://localhost:27017")
db = client["distributed_system"]
issues_collection = db["issues"]
experts_collection = db["experts"]

# Default weights
DEFAULT_WEIGHTS = {
    "skill_match": 0.3,
    "availability": 0.2,
    "trust_score": 0.2,
    "inverse_load": 0.1,
    "nlp_similarity": 0.2   # 🧠 NLP component
}

REGION_WEIGHTS = {
    "expert_weight": 2.0,
    "issue_penalty": 1.0
}

def clean_text(text):
    return re.sub(r"[^a-zA-Z0-9 ]", "", text.lower())

def jaccard_similarity(set1, set2):
    if not set1 or not set2:
        return 0
    return len(set1 & set2) / len(set1 | set2)

def compute_skill_match(issue_text, expert_tags):
    issue_keywords = set(clean_text(issue_text).split())
    tag_keywords = set(tag.lower() for tag in expert_tags)
    return jaccard_similarity(issue_keywords, tag_keywords)

def compute_nlp_similarity(issue_text, expert_tags):
    if not expert_tags:
        return 0.0
    issue_embedding = MODEL.encode(issue_text, convert_to_tensor=True)
    tags_text = " ".join(expert_tags)
    tags_embedding = MODEL.encode(tags_text, convert_to_tensor=True)
    return float(util.pytorch_cos_sim(issue_embedding, tags_embedding).item())

def match_best_expert(issue: dict, experts: list, weights: dict = None, allow_cross_region=True):
    if weights is None:
        weights = DEFAULT_WEIGHTS

    best_expert_id = None
    highest_score = -1

    issue_text = issue.get("title", "") + " " + issue.get("description", "")
    issue_region = issue.get("region")

    regional_experts = [e for e in experts if e.get("region") == issue_region]

    def score_experts(expert_list, label="REGION"):
        nonlocal best_expert_id, highest_score
        for expert in expert_list:
            trust_score = expert.get("trust_score", 0.5)
            active_issues = max(0, int(expert.get("active_issues", 0)))
            inverse_load_score = 1 / (active_issues + 1)

            tags = expert.get("expert_tags", [])
            if isinstance(tags, str):
                tags = [t.strip().lower() for t in tags.split(",")]
            else:
                tags = [t.lower() for t in tags]

            availability_score = 1 if expert.get("availability") == "available" else 0
            skill_score = compute_skill_match(issue_text, tags)
            nlp_score = compute_nlp_similarity(issue_text, tags)

            final_score = (
                weights["skill_match"] * skill_score +
                weights["availability"] * availability_score +
                weights["trust_score"] * trust_score +
                weights["inverse_load"] * inverse_load_score +
                weights["nlp_similarity"] * nlp_score
            )

            # ✅ Log expert scoring
            print(f"\n--- Scoring Expert: {expert.get('email', expert['expert_id'])} ({label}) ---")
            print(f"Tags: {tags}")
            print(f"Availability: {availability_score}, Trust: {trust_score}, Load: {active_issues}")
            print(f"Skill Match: {skill_score:.3f}, NLP Similarity: {nlp_score:.3f}")
            print(f"➡️ Final Score: {final_score:.3f}")

            if final_score > highest_score:
                highest_score = final_score
                best_expert_id = expert["expert_id"]

    # Step 1: Score regional experts
    score_experts(regional_experts, label="REGIONAL")

    # Step 2: Try cross-region if needed
    if allow_cross_region and best_expert_id is None:
        print(f"⚠️ No suitable regional expert, trying cross-region matching...")
        score_experts(experts, label="CROSS-REGION")

    return best_expert_id

# -------------------------------
# 🔄 Get the least Loaded Region
# -------------------------------
def get_best_region():
    regions = ["north", "south", "east", "west"]
    best_region = None
    best_score = float("-inf")

    for region in regions:
        expert_count = experts_collection.count_documents({
            "region": region,
            "is_verified": True,
            "availability": "available"
        })

        issue_count = issues_collection.count_documents({
            "region": region,
            "status": {"$in": ["pending", "assigned", "in_progress"]}
        })

        score = REGION_WEIGHTS["expert_weight"] * expert_count - REGION_WEIGHTS["issue_penalty"] * issue_count

        print(f"[REGION SCORE] {region}: experts={expert_count}, issues={issue_count}, score={score}")

        if score > best_score:
            best_score = score
            best_region = region

    return best_region

async def retry_assignment(issue_id: str):
    await asyncio.sleep(30)  # Wait 30 seconds

    issue = issues_collection.find_one({"issue_id": issue_id})
    if not issue or issue.get("assigned_expert"):
        return  # Already assigned or doesn't exist

    rejected_ids = issue.get("rejected_by", [])
    available_experts = list(experts_collection.find({
        "is_available": True,
        "is_verified": True,
        "expert_id": {"$nin": rejected_ids}
    }))

    new_expert_id = match_best_expert(issue, available_experts)
    if new_expert_id:
        issues_collection.update_one(
            {"issue_id": issue_id},
            {"$set": {"assigned_expert": new_expert_id, "status": "assigned"}}
        )
        experts_collection.update_one({"expert_id": new_expert_id}, {"$inc": {"active_issues": 1}})

        # Notify both user and expert
        await ws_manager.send_event(issue["submitted_by"], "issue_assigned", {"issue_id": issue_id})
        await ws_manager.send_event(new_expert_id, "issue_assigned", {"issue_id": issue_id})
