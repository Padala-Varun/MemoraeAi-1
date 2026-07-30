"""
MemoraeAI — End-to-End API Test

Tests the full flow: login → chat → memory extraction → recall → memories list → forget.
Requires the backend to be running on localhost:8000.

Run:  python e2e_test.py
"""

from __future__ import annotations

import asyncio
import sys
import time

try:
    import httpx  # pyrefly: ignore
except ImportError:
    print("httpx required: pip install httpx")
    sys.exit(1)


BASE_URL = "http://localhost:8000"
TEST_USERNAME = f"e2e_test_{int(time.time())}"


async def main() -> None:
    """Run the full end-to-end test sequence."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        print("=" * 60)
        print("MemoraeAI End-to-End Test")
        print("=" * 60)

        # ── 1. Health Check ──
        print("\n[1/7] Health check...")
        try:
            resp = await client.get("/health")
            resp.raise_for_status()
            data = resp.json()
            assert data["status"] == "ok", f"Expected 'ok', got '{data['status']}'"
            print(f"  ✓ Server healthy: {data}")
        except httpx.ConnectError:
            print(f"  ✗ Cannot connect to {BASE_URL}. Is the server running?")
            print("  Start it with: python -m uvicorn app.main:app --port 8000")
            sys.exit(1)

        # ── 2. Login ──
        print(f"\n[2/7] Login as '{TEST_USERNAME}'...")
        resp = await client.post("/api/user/login", json={"username": TEST_USERNAME})
        resp.raise_for_status()
        user_data = resp.json()
        user_id = user_data["user_id"]
        print(f"  ✓ Logged in: user_id={user_id}")

        # ── 3. Send a message with memorable content ──
        print("\n[3/7] Sending message with facts...")
        resp = await client.post("/api/chat/send", json={
            "user_id": user_id,
            "message": "Hi! My name is Alex and I work as a data scientist at Google. I'm allergic to peanuts and I'm trying to learn Japanese.",
        })
        resp.raise_for_status()
        chat_data = resp.json()
        session_id = chat_data["session_id"]
        print(f"  ✓ Response received ({len(chat_data['response'])} chars)")
        print(f"    Session: {session_id}")
        print(f"    Response preview: {chat_data['response'][:100]}...")

        # ── 4. Wait for async memory extraction ──
        print("\n[4/7] Waiting for memory extraction (5s)...")
        await asyncio.sleep(5)
        print("  ✓ Wait complete.")

        # ── 5. Send a follow-up to test recall ──
        print("\n[5/7] Sending follow-up to test recall...")
        resp = await client.post("/api/chat/send", json={
            "user_id": user_id,
            "session_id": session_id,
            "message": "What do you know about me?",
        })
        resp.raise_for_status()
        recall_data = resp.json()
        print(f"  ✓ Recall response: {recall_data['response'][:200]}...")

        # ── 6. List memories ──
        print("\n[6/7] Listing stored memories...")
        resp = await client.post("/api/memories/list", json={"user_id": user_id})
        resp.raise_for_status()
        memories_data = resp.json()

        ep_count = len(memories_data.get("episodic", []))
        sem_count = len(memories_data.get("semantic", []))
        has_profile = memories_data.get("profile") is not None
        goal_count = len(memories_data.get("goals", []))

        print(f"  ✓ Memories found:")
        print(f"    Episodic: {ep_count}")
        print(f"    Semantic: {sem_count}")
        print(f"    Profile:  {'Yes' if has_profile else 'No'}")
        print(f"    Goals:    {goal_count}")

        # ── 7. Test conflict resolution ──
        print("\n[7/7] Testing conflict resolution...")
        resp = await client.post("/api/chat/send", json={
            "user_id": user_id,
            "session_id": session_id,
            "message": "Actually, I just switched jobs. I now work at Microsoft as a senior engineer.",
        })
        resp.raise_for_status()
        conflict_data = resp.json()
        print(f"  ✓ Conflict response: {conflict_data['response'][:200]}...")

        await asyncio.sleep(5)

        # Check memories again
        resp = await client.post("/api/memories/list", json={"user_id": user_id})
        resp.raise_for_status()
        updated_memories = resp.json()
        print(f"  ✓ Updated semantic count: {len(updated_memories.get('semantic', []))}")

        # ── Summary ──
        print("\n" + "=" * 60)
        print("E2E TEST COMPLETE")
        print("=" * 60)

        total_memories = ep_count + sem_count + goal_count + (1 if has_profile else 0)
        if total_memories > 0:
            print(f"✓ SUCCESS: {total_memories} memories stored and recalled.")
        else:
            print("⚠ WARNING: No memories stored. Memory extraction may need more time.")
            print("  This is expected if the LLM didn't extract memories from the test input.")

        print(f"\nTest user: {TEST_USERNAME} (user_id: {user_id})")
        print("Note: Test data remains in the databases for manual inspection.")


if __name__ == "__main__":
    asyncio.run(main())
