"""Seed the composio_connections collection in MongoDB."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from motor.motor_asyncio import AsyncIOMotorClient


async def seed():
    client = AsyncIOMotorClient(os.getenv("MONGODB_URI"))
    db = client[os.getenv("MONGODB_DATABASE")]

    # Find the first user in the system
    user = await db["users"].find_one()
    if user:
        user_id = user["user_id"]
        username = user.get("username", "unknown")
    else:
        user_id = "default-user"
        username = "default"

    print(f"Found user: {username} ({user_id})")

    # Store the Gmail connection mapping
    result = await db["composio_connections"].update_one(
        {"connected_account_id": "ca_AGmOWsEWdqQ9"},
        {
            "$set": {
                "user_id": user_id,
                "provider": "gmail",
                "connected_account_id": "ca_AGmOWsEWdqQ9",
                "composio_user_id": "pg-test-d7368a8c-b688-44d0-a5bf-2ef37b1db5dd",
                "trigger_id": "ti_TP4HccHr6P-p",
                "status": "active",
            }
        },
        upsert=True,
    )
    print(f"Connection mapping saved (upserted={result.upserted_id})")

    # Verify
    conn = await db["composio_connections"].find_one({"provider": "gmail"})
    print(f"Verified: user_id={conn['user_id']}, account={conn['connected_account_id']}")

    client.close()


asyncio.run(seed())
