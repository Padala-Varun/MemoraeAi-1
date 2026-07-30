"""One-off: Mark the old 'favorite_hero → jr. ntr' semantic fact as outdated
in both Neo4j and Qdrant, since the user's new favorite is 'Mahesh Babu'.

Uses the app's own semantic_pipeline._mark_qdrant_fact_outdated() and
Neo4j Cypher to keep the fix consistent with production logic.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # pyrefly: ignore
load_dotenv()

from app.config import get_settings  # pyrefly: ignore
from app.db_clients import get_neo4j_driver, get_qdrant_client  # pyrefly: ignore
from datetime import datetime, timezone  # pyrefly: ignore


async def fix_neo4j() -> None:
    """Mark user → favorite_hero → jr. ntr as outdated in Neo4j."""
    settings = get_settings()
    driver = get_neo4j_driver()
    now = datetime.now(timezone.utc).isoformat()

    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        # Find and mark outdated
        result = await session.run(
            """
            MATCH (s:Entity {name: 'user'})
                  -[r:RELATES_TO {predicate: 'favorite_hero', status: 'active'}]->
                  (o:Entity)
            WHERE o.name <> 'mahesh babu'
            SET r.status = 'outdated', r.outdated_at = datetime($now)
            RETURN s.name AS subject, r.predicate AS predicate, o.name AS object
            """,
            now=now,
        )

        records = [record async for record in result]
        if records:
            for rec in records:
                print(f"Neo4j: Marked outdated: ({rec['subject']}, {rec['predicate']}, {rec['object']})")
        else:
            print("Neo4j: No stale favorite_hero relationships found.")

    await driver.close()


def fix_qdrant() -> None:
    """Mark old favorite_hero facts as outdated in Qdrant."""
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue  # pyrefly: ignore

    settings = get_settings()
    client = get_qdrant_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    results = client.scroll(
        collection_name=settings.QDRANT_SEMANTIC_COLLECTION,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="status", match=MatchValue(value="active")),
            ]
        ),
        limit=100,
        with_payload=True,
    )

    for point in results[0]:
        payload = point.payload or {}
        pred = payload.get("predicate", "")
        obj = payload.get("object", "")
        if pred == "favorite_hero" and obj.lower() != "mahesh babu":
            client.set_payload(
                collection_name=settings.QDRANT_SEMANTIC_COLLECTION,
                payload={"status": "outdated", "outdated_at": now_iso},
                points=[point.id],
            )
            print(f"Qdrant: Marked outdated: ({payload.get('subject')}, {payload.get('predicate')}, {obj})")
        else:
            print(f"Qdrant: Kept active: ({payload.get('subject')}, {payload.get('predicate')}, {obj})")

    if not results[0]:
        print("Qdrant: No active favorite_hero facts found.")


async def main() -> None:
    print("=== Fixing stale semantic facts ===\n")
    await fix_neo4j()
    print()
    fix_qdrant()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
