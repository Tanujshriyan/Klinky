from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def send_expo_push(
    token: str,
    *,
    title: str,
    body: str,
    data: dict | None = None,
) -> None:
    """Best-effort Expo push dispatch. Requires EAS/APNs/FCM credentials in production."""
    if not token or not token.startswith("ExponentPushToken"):
        return
    payload = json.dumps(
        {
            "to": token,
            "title": title,
            "body": body,
            "data": data or {},
            "sound": "default",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://exp.host/--/api/v2/push/send",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning("Expo push dispatch failed: %s", exc)


def dispatch_message_push(recipient_id: str, sender_name: str, conversation_id: str) -> None:
    from app.store import store

    recipient = store.users.get(recipient_id)
    if not recipient or not recipient.pushToken:
        return
    send_expo_push(
        recipient.pushToken,
        title=sender_name or "New message",
        body="Sent you a message",
        data={"type": "message", "conversationId": conversation_id},
    )


def dispatch_profile_push(recipient_id: str, *, title: str, body: str, user_id: str, push_type: str) -> None:
    from app.store import store

    recipient = store.users.get(recipient_id)
    if not recipient or not recipient.pushToken:
        return
    send_expo_push(
        recipient.pushToken,
        title=title,
        body=body,
        data={"type": push_type, "userId": user_id},
    )
