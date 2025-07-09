from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
from app.auth.auth_handler import create_access_token
from datetime import timedelta
import bcrypt
import uuid

router = APIRouter()

client = MongoClient("mongodb://localhost:27017")
db = client["distributed_system"]
users_collection = db["users"]
experts_collection = db["experts"]

ADMIN_EMAILS = ["admin@example.com"]  # Add more as needed

# ---------------------
# SCHEMAS
# ---------------------
class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str  # "user" or "expert"
    proof_resume: str = ""
    qualifications: str = ""
    experience_years: int = 0
    portfolio_url: str = ""
    quiz_score: int = 0
    region: str

class LoginRequest(BaseModel):
    email: str
    password: str

# ---------------------
# REGISTER
# ---------------------
@router.post("/register")
def register(data: RegisterRequest):
    if users_collection.find_one({"email": data.email}) or experts_collection.find_one({"email": data.email}):
        raise HTTPException(status_code=400, detail="Email already registered.")

    hashed_pw = bcrypt.hashpw(data.password.encode('utf-8'), bcrypt.gensalt())
    user_id = str(uuid.uuid4())

    if data.role == "expert":
        expert = {
            "expert_id": user_id,
            "name": data.name,
            "email": data.email,
            "password": hashed_pw,
            "skills": [],
            "categories": [],
            "max_concurrent_issues": 3,
            "is_available": False,
            "active_issues": 0,
            "trust_score": 0.5,
            "trust_votes": 1,
            "proof_resume": data.proof_resume,
            "qualifications": data.qualifications,
            "experience_years": data.experience_years,
            "portfolio_url": data.portfolio_url,
            "quiz_score": data.quiz_score,
            "is_verified": False,
            "verification_notes": "",
            "region": data.region,
        }
        experts_collection.insert_one(expert)

    elif data.role == "user":
        user = {
            "user_id": user_id,
            "name": data.name,
            "email": data.email,
            "password": hashed_pw,
            "trust_score": 0.5,
            "region": data.region,
        }
        users_collection.insert_one(user)

    else:
        raise HTTPException(status_code=400, detail="Invalid role.")

    return {"message": f"{data.role.capitalize()} registered successfully."}

# ---------------------
# LOGIN
# ---------------------
@router.post("/login")
def login(data: LoginRequest):
    user = users_collection.find_one({"email": data.email})
    role = "user"
    user_id = None

    if not user:
        user = experts_collection.find_one({"email": data.email})
        role = "expert"

    if not user:
        raise HTTPException(status_code=401, detail="Email not found.")

    stored_pw = user.get("password")
    if stored_pw is None:
        raise HTTPException(status_code=500, detail="Corrupted user entry: password missing.")
    if isinstance(stored_pw, str):
        stored_pw = stored_pw.encode('utf-8')
    elif hasattr(stored_pw, 'decode'):
        stored_pw = stored_pw.decode('utf-8').encode('utf-8')  # For Mongo Binary object

    if not bcrypt.checkpw(data.password.encode('utf-8'), stored_pw):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    if user["email"] in ADMIN_EMAILS:
        role = "admin"

    user_id = user.get("user_id") or user.get("expert_id")

    token = create_access_token({
        "sub": user_id,
        "role": role,
        "email": user["email"],
        "region": user.get("region")
    }, expires_delta=timedelta(hours=1))

    return {
        "access_token": token,
        "user_id": user_id,
        "role": role
    }
