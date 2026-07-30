"""
Composio Setup Script — One-time configuration for Gmail integration.

Registers the webhook callback URL with Composio, enables the
GMAIL_NEW_GMAIL_MESSAGE trigger, and optionally initiates a Gmail
account connection.

Usage:
    python scripts/setup_composio.py
    python scripts/setup_composio.py --connect-gmail
"""

from __future__ import annotations

import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


WEBHOOK_URL = "https://varun1432varun1432--memorae-ai-web.modal.run/api/webhooks/composio"


def setup_composio() -> None:
    """Register webhook URL and enable Gmail trigger."""
    from composio import Composio

    api_key = os.getenv("COMPOSIO_API_KEY")
    if not api_key:
        print("ERROR: COMPOSIO_API_KEY not set in .env")
        sys.exit(1)

    print("Initializing Composio client...")
    client = Composio(api_key=api_key)

    # Step 1: Set webhook URL via the API
    print(f"\n1. Setting webhook URL: {WEBHOOK_URL}")
    try:
        # Try the v0.18 API for setting callback URL
        if hasattr(client, "triggers") and hasattr(client.triggers, "set_callback_url"):
            client.triggers.set_callback_url(WEBHOOK_URL)
            print("   [OK] Webhook callback URL set via triggers.set_callback_url()")
        elif hasattr(client, "set_global_trigger_callback"):
            client.set_global_trigger_callback(WEBHOOK_URL)
            print("   [OK] Webhook callback URL set via set_global_trigger_callback()")
        else:
            # Use the REST API directly
            import httpx
            resp = httpx.patch(
                "https://backend.composio.dev/api/v1/triggers/set_callback_url",
                json={"callbackURL": WEBHOOK_URL},
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            if resp.status_code < 300:
                print(f"   [OK] Webhook URL set via REST API (status={resp.status_code})")
            else:
                print(f"   [WARN] REST API returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"   [WARN] Webhook registration: {e}")
        print("   (You may need to set the webhook URL manually in the Composio dashboard)")

    # Step 2: List connected accounts
    print("\n2. Checking connected accounts...")
    try:
        accounts = client.connected_accounts.list()
        if accounts:
            count = len(accounts) if hasattr(accounts, "__len__") else "?"
            print(f"   Found {count} connected account(s):")
            for acc in accounts:
                acc_id = getattr(acc, "id", "unknown")
                status = getattr(acc, "status", "unknown")
                app_name = getattr(acc, "app_name", getattr(acc, "toolkit_slug", "unknown"))
                print(f"     - {app_name}: id={acc_id}, status={status}")
        else:
            print("   No connected accounts found.")
            print("   Use --connect-gmail to initiate a connection.")
    except Exception as e:
        print(f"   [WARN] Could not list accounts: {e}")

    # Step 3: Check triggers
    print("\n3. Checking triggers...")
    try:
        if hasattr(client, "triggers") and hasattr(client.triggers, "list"):
            triggers = client.triggers.list()
            if triggers:
                count = len(triggers) if hasattr(triggers, "__len__") else "?"
                print(f"   Found {count} trigger(s)")
            else:
                print("   No triggers found yet.")
        else:
            print("   Trigger listing not available in this SDK version.")
    except Exception as e:
        print(f"   [WARN] Could not list triggers: {e}")

    print("\n[DONE] Composio setup complete!")
    print(f"  Webhook URL: {WEBHOOK_URL}")
    print(f"  Trigger: GMAIL_NEW_GMAIL_MESSAGE (polling ~15min)")


def connect_gmail() -> None:
    """Initiate a Gmail OAuth connection via Composio."""
    from composio import Composio

    api_key = os.getenv("COMPOSIO_API_KEY")
    if not api_key:
        print("ERROR: COMPOSIO_API_KEY not set in .env")
        sys.exit(1)

    client = Composio(api_key=api_key)

    print("Initiating Gmail connection via Composio...")
    try:
        connection = client.connected_accounts.initiate(
            integration_id="gmail",
            entity_id="default-user",
            redirect_url="https://memorae-ai-1.vercel.app/chat.html",
        )

        redirect_url = getattr(connection, "redirect_url", None)
        connected_id = getattr(connection, "connected_account_id", None)

        print(f"\n[OK] Connection initiated!")
        print(f"  Connected Account ID: {connected_id}")
        if redirect_url:
            print(f"  OAuth URL: {redirect_url}")
            print(f"\n  Open this URL in your browser to authorize Gmail access.")
        else:
            print(f"  Response: {connection}")
    except Exception as e:
        print(f"ERROR: Failed to initiate Gmail connection: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up Composio Gmail integration for MemoraeAI")
    parser.add_argument(
        "--connect-gmail",
        action="store_true",
        help="Initiate a Gmail OAuth connection",
    )
    args = parser.parse_args()

    setup_composio()

    if args.connect_gmail:
        print("\n" + "=" * 50)
        connect_gmail()
