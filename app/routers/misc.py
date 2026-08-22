from fastapi import APIRouter, Depends, Response

from app.auth import CurrentUserId
from app.errors import api_error
from app.models import PresignUploadRequest, TrackTouchEventInput
from app.store import store

router = APIRouter(tags=["misc"])


@router.get("/settings")
def get_settings(_user_id: str = CurrentUserId):
    return store.get_settings()


@router.patch("/settings")
def update_settings(body: dict, _user_id: str = CurrentUserId):
    if "premium" in body and len(body) == 1:
        return store.set_premium(body["premium"])
    return store.update_settings(body)


@router.post("/touch-events")
def track_touch_event(body: TrackTouchEventInput, user_id: str = CurrentUserId):
    payload = body.model_copy(update={"actorUserId": user_id})
    return store.track_touch_event(payload)


@router.get("/favorites")
def get_favorites(_user_id: str = CurrentUserId):
    return store.get_favorite_users()


@router.get("/favorites/{user_id}")
def is_favorite(user_id: str, _user_id: str = CurrentUserId):
    return {"favorite": store.is_favorite(user_id)}


@router.post("/favorites", status_code=204)
def add_favorite(body: dict, _user_id: str = CurrentUserId):
    store.add_favorite(body["userId"])
    return Response(status_code=204)


@router.delete("/favorites/{user_id}", status_code=204)
def remove_favorite(user_id: str, _user_id: str = CurrentUserId):
    store.remove_favorite(user_id)
    return Response(status_code=204)


@router.get("/blocks")
def get_blocked_ids(_user_id: str = CurrentUserId):
    return store.get_blocked_ids()


@router.get("/blocks/users")
def get_blocked_users(_user_id: str = CurrentUserId):
    return store.get_blocked_users()


@router.post("/blocks", status_code=204)
def block_user(body: dict, _user_id: str = CurrentUserId):
    store.block_user(body["userId"])
    return Response(status_code=204)


@router.delete("/blocks/{user_id}", status_code=204)
def unblock_user(user_id: str, _user_id: str = CurrentUserId):
    store.unblock_user(user_id)
    return Response(status_code=204)


@router.post("/reports")
def report_user(body: dict, user_id: str = CurrentUserId):
    return store.report_user(
        body["userId"],
        body["reason"],
        body.get("conversationId"),
        body.get("details"),
        reporter_user_id=user_id,
    )


@router.get("/reports")
def get_reports(user_id: str = CurrentUserId):
    return store.get_reports(reporter_user_id=user_id)


@router.get("/notifications")
def get_notifications(_user_id: str = CurrentUserId):
    return store.get_notifications()


@router.get("/notifications/unread-count")
def unread_notification_count(_user_id: str = CurrentUserId):
    return {"count": store.get_unread_notification_count()}


@router.post("/notifications")
def create_notification(_user_id: str = CurrentUserId):
    raise api_error("API_006", "You do not have permission for this action.", 403, "Notifications are server-only.")


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_notification_read(notification_id: str, _user_id: str = CurrentUserId):
    store.mark_notification_read(notification_id)
    return Response(status_code=204)


@router.post("/notifications/read-all", status_code=204)
def mark_all_notifications_read(_user_id: str = CurrentUserId):
    store.mark_all_notifications_read()
    return Response(status_code=204)


@router.post("/uploads/presign")
def presign_upload(body: PresignUploadRequest, user_id: str = CurrentUserId):
    return store.create_presigned_upload(body, user_id)


@router.post("/moderation/scan")
def scan_media(body: dict, _user_id: str = CurrentUserId):
    return store.scan_media(
        body.get("fileName", ""),
        content_type=body.get("contentType"),
        file_size=body.get("fileSizeBytes"),
        kind=body.get("kind"),
    )
