"""Check all users and fix Gmail mapping."""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient

async def check_and_fix():
    client = AsyncIOMotorClient(os.getenv("MONGODB_URI"))
    db = client[os.getenv("MONGODB_DATABASE")]

    print("=== All Users ===")
    users = []
    async for user in db["users"].find():
        uid = user["user_id"]
        uname = user.get("username", "?")
        print(f"  {uname} -> {uid}")
        users.append(user)

    print("\n=== Current Gmail Mapping ===")
    conn = await db["composio_connections"].find_one({"provider": "gmail"})
    if conn:
        print(f"  Maps to user_id: {conn['user_id']}")

    # The chat user is b455826c-31f3-40d0-a1e7-6d7f999173d5
    # Fix the mapping
    chat_user_id = "b455826c-31f3-40d0-a1e7-6d7f999173d5"
    print(f"\n=== Fixing mapping to {chat_user_id} ===")
    result = await db["composio_connections"].update_one(
        {"provider": "gmail"},
        {"$set": {"user_id": chat_user_id}},
    )
    print(f"  Modified: {result.modified_count}")

    # Verify
    conn = await db["composio_connections"].find_one({"provider": "gmail"})
    print(f"  New mapping: user_id={conn['user_id']}")

    client.close()

asyncio.run(check_and_fix())
