"""Short-lived WebSocket connection tickets (avoid JWT in query strings)."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

TICKET_TTL_SECONDS = 60


@dataclass
class WsTicket:
    user_id: str
    expires_at: datetime


_tickets: dict[str, WsTicket] = {}


def issue_ws_ticket(user_id: str) -> str:
    _purge_expired()
    ticket = secrets.token_urlsafe(32)
    _tickets[ticket] = WsTicket(
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=TICKET_TTL_SECONDS),
    )
    return ticket


def consume_ws_ticket(ticket: str) -> str | None:
    _purge_expired()
    entry = _tickets.pop(ticket, None)
    if not entry or entry.expires_at < datetime.now(timezone.utc):
        return None
    return entry.user_id


resolve_ws_ticket = consume_ws_ticket


def _purge_expired() -> None:
    now = datetime.now(timezone.utc)
    expired = [key for key, value in _tickets.items() if value.expires_at < now]
    for key in expired:
        _tickets.pop(key, None)
