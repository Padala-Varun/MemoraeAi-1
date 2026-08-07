"""Unit tests for Gmail / Composio email parsing helpers (no DB, no LLM)."""

from __future__ import annotations

from app.composio_integration import (
    format_email_as_conversation,
    parse_email_from_trigger,
)


def test_parse_email_v3_payload():
    """Parse Composio v3 webhook shape with email fields under data."""
    payload = {
        "type": "gmail_new_gmail_message",
        "metadata": {
            "trigger_slug": "GMAIL_NEW_GMAIL_MESSAGE",
            "connected_account_id": "ca_test_123",
        },
        "data": {
            "subject": "Project deadline moved",
            "messageText": "The launch date is now Friday.",
            "from": "alice@company.com",
            "threadId": "thread-1",
            "messageId": "msg-1",
        },
    }

    email = parse_email_from_trigger(payload)
    assert email["subject"] == "Project deadline moved"
    assert email["body"] == "The launch date is now Friday."
    assert email["sender"] == "alice@company.com"
    assert email["thread_id"] == "thread-1"
    assert email["message_id"] == "msg-1"


def test_parse_email_falls_back_to_snippet():
    """When body is empty, use preview/snippet as body."""
    payload = {
        "data": {
            "subject": "Quick update",
            "snippet": "See you at standup.",
            "from": "bob@company.com",
        }
    }

    email = parse_email_from_trigger(payload)
    assert email["subject"] == "Quick update"
    assert email["body"] == "See you at standup."
    assert email["sender"] == "bob@company.com"


def test_format_email_as_conversation():
    """Formatted email should look like conversation text for the detector."""
    text = format_email_as_conversation(
        {
            "sender": "alice@company.com",
            "subject": "Sprint goals",
            "body": "Finish auth by Friday.",
            "timestamp": "2026-08-01T10:00:00+00:00",
        }
    )

    assert "Email from: alice@company.com" in text
    assert "Subject: Sprint goals" in text
    assert "Content: Finish auth by Friday." in text
    assert "Received at: 2026-08-01T10:00:00+00:00" in text


def test_format_email_empty_fields():
    """Empty email data should produce an empty or blank string."""
    text = format_email_as_conversation({})
    assert text.strip() == ""
