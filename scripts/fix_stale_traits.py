"""One-off script: remove the stale 'Jr. NTR' trait from all profiles
that also have the newer 'Allu Arjun' trait, so only the latest survives.

Uses the project .env for the correct MongoDB Atlas URI.
"""

import asyncio
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # pyrefly: ignore
from motor.motor_asyncio import AsyncIOMotorClient  # pyrefly: ignore

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DATABASE", "memorae_ai")
COLLECTION = "profiles"


async def main() -> None:
    print(f"Connecting to: {MONGO_URI[:40]}...")
    client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)  # pyrefly: ignore
    db = client[DB_NAME]
    col = db[COLLECTION]

    # Find all profiles
    count = 0
    async for doc in col.find({}, {"user_id": 1, "traits": 1}):
        count += 1
        user_id = doc.get("user_id", "?")
        traits: list[str] = doc.get("traits", [])
        print(f"\nUser '{user_id}': {len(traits)} traits")
        for i, t in enumerate(traits):
            print(f"  [{i}] {t}")

        if not traits:
            continue

        # Group traits by rough topic and keep only the LATEST (last in array)
        stale: list[str] = []
        seen_topics: dict[str, str] = {}

        for trait in traits:
            lower = trait.lower()
            # Extract a rough key: everything before "is"/"are"
            if " is " in lower:
                key = lower.split(" is ")[0].strip()
            elif " are " in lower:
                key = lower.split(" are ")[0].strip()
            else:
                key = lower

            if key in seen_topics:
                # Conflict! The LATER trait wins (it was added more recently)
                stale.append(seen_topics[key])  # Mark the OLDER one as stale
                seen_topics[key] = trait  # Keep the newer
            else:
                seen_topics[key] = trait

        if stale:
            print(f"  -> REMOVING stale traits: {stale}")
            result = await col.update_one(
                {"user_id": user_id},
                {"$pull": {"traits": {"$in": stale}}},
            )
            print(f"  -> Modified: {result.modified_count}")
        else:
            print(f"  -> No conflicts")

    if count == 0:
        print("No profiles found in the database.")

    client.close()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
