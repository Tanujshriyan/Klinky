from fastapi import APIRouter, Depends, Response

from app.auth import CurrentUserId
from app.errors import api_error
from app.models import CreateEventInput, UpdateEventInput
from app.store import store

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
def get_events(
    filter: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    _user_id: str = CurrentUserId,
):
    me = store.get_current_user()
    return store.get_events(filter, lat if lat is not None else me.latitude, lng if lng is not None else me.longitude)


@router.post("/notify-new")
def notify_new_nearby_events(_user_id: str = CurrentUserId):
    me = store.get_current_user()
    count = store.notify_new_nearby_events(me.latitude, me.longitude)
    return {"count": count}


@router.get("/{event_id}")
def get_event(event_id: str, _user_id: str = CurrentUserId):
    event = store.get_event(event_id)
    if not event:
        raise api_error("API_003", "The requested resource was not found.", 404)
    return event


@router.post("")
def create_event(body: CreateEventInput, _user_id: str = CurrentUserId):
    me = store.get_current_user()
    return store.create_event(body, me.latitude, me.longitude)


@router.patch("/{event_id}")
def update_event(event_id: str, body: UpdateEventInput, _user_id: str = CurrentUserId):
    event = store.update_event(event_id, body)
    if not event:
        raise api_error("API_003", "The requested resource was not found.", 404)
    return event


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: str, _user_id: str = CurrentUserId):
    store.delete_event(event_id)
    return Response(status_code=204)


@router.post("/{event_id}/rsvp")
def rsvp_event(event_id: str, _user_id: str = CurrentUserId):
    event = store.rsvp_event(event_id)
    if not event:
        raise api_error("API_003", "The requested resource was not found.", 404)
    return event


@router.delete("/{event_id}/rsvp")
def cancel_rsvp(event_id: str, _user_id: str = CurrentUserId):
    event = store.cancel_rsvp(event_id)
    if not event:
        raise api_error("API_003", "The requested resource was not found.", 404)
    return event


@router.get("/{event_id}/attendees")
def get_event_attendees(event_id: str, _user_id: str = CurrentUserId):
    return store.get_event_attendees(event_id)
