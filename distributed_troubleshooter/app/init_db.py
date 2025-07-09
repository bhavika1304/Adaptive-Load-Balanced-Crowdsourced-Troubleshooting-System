from pymongo import MongoClient
from datetime import datetime

client = MongoClient("mongodb://localhost:27017")
db = client["distributed_system"]

# Collections to initialize
messages_collection = db["messages"]

# Dummy message to create 'messages' collection
dummy_message = {
    "issue_id": "issue_id",
    "sender_id": "None",
    "sender_role": "system",
    "content": "Issue created.",
    "timestamp": datetime.utcnow()
}

# Insert and delete to trigger creation
messages_collection.insert_one(dummy_message)
messages_collection.delete_one({"issue_id": "dummy123"})

print("✅ MongoDB collections initialized.")
