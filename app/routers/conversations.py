from fastapi import APIRouter, Depends, Response

from app.auth import CurrentUserId
from app.errors import api_error
from app.store import store

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
def get_conversations(_user_id: str = CurrentUserId):
    return store.get_conversations()


@router.post("/conversations")
def create_conversation(body: dict, _user_id: str = CurrentUserId):
    return store.create_conversation(body["participantId"])


@router.post("/conversations/group")
def create_group_conversation(body: dict, _user_id: str = CurrentUserId):
    return store.create_group_conversation(body.get("participantIds", []), body.get("title", ""))


@router.get("/conversations/{conversation_id}/messages")
def get_messages(
    conversation_id: str,
    cursor: str | None = None,
    limit: int = 50,
    _user_id: str = CurrentUserId,
):
    return store.get_messages(conversation_id, cursor, limit)


@router.post("/conversations/{conversation_id}/read", status_code=204)
def mark_conversation_read(conversation_id: str, _user_id: str = CurrentUserId):
    store.mark_conversation_read(conversation_id)
    return Response(status_code=204)


@router.patch("/messages/{message_id}")
def edit_message(message_id: str, body: dict, _user_id: str = CurrentUserId):
    msg = store.edit_message(message_id, body.get("body", ""))
    if not msg:
        raise api_error("API_003", "The requested resource was not found.", 404)
    return msg


@router.delete("/messages/{message_id}")
def delete_message(message_id: str, _user_id: str = CurrentUserId):
    msg = store.delete_message(message_id)
    if not msg:
        raise api_error("API_003", "The requested resource was not found.", 404)
    return msg


@router.post("/messages/{message_id}/viewed")
def mark_message_viewed(message_id: str, body: dict, _user_id: str = CurrentUserId):
    msg = store.mark_message_viewed(message_id, body.get("viewedAt"))
    if not msg:
        raise api_error("API_003", "The requested resource was not found.", 404)
    return msg
