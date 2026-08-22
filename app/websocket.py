from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.auth import decode_token
from app.errors import ApiError
from app.models import Message, new_id
from app.store import store
from app.push_dispatch import dispatch_message_push
from app.ws_tickets import resolve_ws_ticket

MAX_WS_MESSAGE_BYTES = 65536


def _is_conversation_member(user_id: str, conversation_id: str) -> bool:
    return user_id in store.conversation_participant_ids(conversation_id)


class ChatConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        self.connections.setdefault(user_id, set()).add(websocket)
        store.users[user_id].isOnline = True
        await self._broadcast_presence(user_id, True)

    def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        conns = self.connections.get(user_id, set())
        conns.discard(websocket)
        if not conns:
            self.connections.pop(user_id, None)
            if user_id in store.users:
                store.users[user_id].isOnline = False

    async def handle(self, websocket: WebSocket, user_id: str) -> None:
        try:
            while True:
                raw = await websocket.receive_text()
                if len(raw.encode("utf-8")) > MAX_WS_MESSAGE_BYTES:
                    await websocket.send_json({"type": "error", "code": "MSG_TOO_LARGE", "message": "Message too large."})
                    continue
                event = json.loads(raw)
                await self._handle_event(websocket, user_id, event)
        except WebSocketDisconnect:
            self.disconnect(websocket, user_id)
            await self._broadcast_presence(user_id, False)

    async def _handle_event(self, websocket: WebSocket, user_id: str, event: dict) -> None:
        event_type = event.get("type")
        if event_type == "ping":
            await websocket.send_json({"type": "pong"})
            return
        if event_type == "message.send":
            conversation_id = event.get("conversationId")
            if not conversation_id or not _is_conversation_member(user_id, conversation_id):
                await websocket.send_json({"type": "error", "code": "FORBIDDEN", "message": "Not a conversation member."})
                return
            await self._handle_send(websocket, user_id, event)
            return
        if event_type == "typing.start":
            conversation_id = event.get("conversationId")
            if not conversation_id or not _is_conversation_member(user_id, conversation_id):
                return
            await self._broadcast_to_conversation(
                conversation_id,
                {"type": "typing.start", "conversationId": conversation_id, "userId": user_id},
                exclude=user_id,
            )
            return
        if event_type == "typing.stop":
            conversation_id = event.get("conversationId")
            if not conversation_id or not _is_conversation_member(user_id, conversation_id):
                return
            await self._broadcast_to_conversation(
                conversation_id,
                {"type": "typing.stop", "conversationId": conversation_id, "userId": user_id},
                exclude=user_id,
            )
            return
        if event_type == "message.read":
            conversation_id = event.get("conversationId")
            if not conversation_id or not _is_conversation_member(user_id, conversation_id):
                return
            store.mark_conversation_read(conversation_id)
            await self._broadcast_to_conversation(
                conversation_id,
                {
                    "type": "message.read",
                    "conversationId": conversation_id,
                    "messageId": event["messageId"],
                    "readBy": user_id,
                },
            )
            return
        if event_type == "message.viewed":
            conversation_id = event.get("conversationId")
            if not conversation_id or not _is_conversation_member(user_id, conversation_id):
                return
            viewed_at = datetime.now(timezone.utc).isoformat()
            updated = store.mark_message_viewed(event["messageId"], viewed_at)
            if updated:
                payload = {
                    "type": "message.viewed",
                    "conversationId": conversation_id,
                    "messageId": event["messageId"],
                    "viewedAt": updated.viewedAt or viewed_at,
                    "viewedBy": user_id,
                }
                await self._broadcast_to_conversation(conversation_id, payload)
            return

    async def _handle_send(self, websocket: WebSocket, user_id: str, event: dict) -> None:
        conversation_id = event.get("conversationId", "")
        if store._conversation_has_block(conversation_id):
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "API_006",
                    "message": "You do not have permission for this action.",
                }
            )
            return
        client_id = event.get("clientId", new_id("client"))
        existing = store.find_message_by_client_id(client_id)
        if existing:
            message = existing.model_copy()
        else:
            message = Message(
                id=new_id("msg"),
                conversationId=conversation_id,
                senderId=user_id,
                body=event.get("body", ""),
                createdAt=datetime.now(timezone.utc).isoformat(),
                status="sent",
                clientId=client_id,
                mediaUrl=event.get("mediaUrl"),
                mediaType=event.get("mediaType"),
                thumbnailUrl=event.get("thumbnailUrl"),
                viewOnce=event.get("viewOnce"),
                viewedAt=None if event.get("viewOnce") else None,
            )
            try:
                store.add_message(message)
            except ApiError as exc:
                await websocket.send_json({"type": "error", "code": exc.code, "message": exc.message})
                return
        delivered = message.model_copy(update={"status": "delivered"})
        await self._send_to_user(user_id, {"type": "message.ack", "clientId": client_id, "message": delivered.model_dump()})
        await self._broadcast_to_conversation(
            conversation_id,
            {"type": "message.new", "message": delivered.model_dump()},
        )
        sender = store.users.get(user_id)
        sender_name = sender.displayName if sender else "Someone"
        for participant_id in store.conversation_participant_ids(conversation_id):
            if participant_id == user_id:
                continue
            dispatch_message_push(participant_id, sender_name, conversation_id)

    async def _send_to_user(self, user_id: str, payload: dict) -> None:
        for ws in list(self.connections.get(user_id, set())):
            await ws.send_json(payload)

    async def _broadcast_to_conversation(self, conversation_id: str, payload: dict, exclude: str | None = None) -> None:
        for participant_id in store.conversation_participant_ids(conversation_id):
            if exclude and participant_id == exclude:
                continue
            for ws in list(self.connections.get(participant_id, set())):
                await ws.send_json(payload)

    async def _broadcast_presence(self, user_id: str, is_online: bool) -> None:
        payload = {"type": "presence.update", "userId": user_id, "isOnline": is_online}
        related = set()
        for conv in store.conversations:
            if user_id in conv.participantIds:
                related.update(conv.participantIds)
        related.discard(user_id)
        for other_id in related:
            for ws in list(self.connections.get(other_id, set())):
                await ws.send_json(payload)


chat_manager = ChatConnectionManager()


async def chat_websocket(websocket: WebSocket, token: str | None, ticket: str | None) -> None:
    user_id: str | None = None
    if ticket:
        user_id = resolve_ws_ticket(ticket)
    elif token:
        try:
            user_id = decode_token(token).sub
        except Exception:
            user_id = None
    if not user_id:
        await websocket.close(code=4001)
        return
    await chat_manager.connect(websocket, user_id)
    await chat_manager.handle(websocket, user_id)
