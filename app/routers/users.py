from fastapi import APIRouter, Response

from app.auth import CurrentUserId
from app.errors import api_error
from app.models import ConsentInput, PushTokenInput, UpdateProfileInput
from app.store import store

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def get_current_user(_user_id: str = CurrentUserId):
    return store.get_current_user()


@router.patch("/me")
def update_profile(body: UpdateProfileInput, _user_id: str = CurrentUserId):
    return store.update_profile(body)


@router.patch("/me/push-token")
def update_push_token(body: PushTokenInput, _user_id: str = CurrentUserId):
    return store.update_push_token(body.token)


@router.post("/me/verify")
def request_verification(_user_id: str = CurrentUserId):
    return store.request_verification()


@router.post("/me/boost")
def boost_profile(_user_id: str = CurrentUserId):
    return store.boost_profile()


@router.post("/me/consents")
def record_consent(body: ConsentInput, _user_id: str = CurrentUserId):
    return store.record_consent(body.type, body.version)


@router.post("/me/data-export")
def request_data_export(_user_id: str = CurrentUserId):
    return store.request_data_export()


@router.get("/me/data-export/{request_id}")
def get_data_export_status(request_id: str, _user_id: str = CurrentUserId):
    return store.get_data_export_status(request_id)


@router.get("/nearby")
def get_nearby_users(
    lat: float,
    lng: float,
    radius: float = 5000,
    online_only: bool = False,
    hosting_only: bool = False,
    age_min: int = 18,
    age_max: int = 99,
    sort: str = "distance",
    _user_id: str = CurrentUserId,
):
    return store.get_nearby_users(lat, lng, radius, online_only, hosting_only, age_min, age_max, sort)


@router.get("/{user_id}")
def get_user(user_id: str, _user_id: str = CurrentUserId):
    user = store.get_user(user_id)
    if not user:
        raise api_error("API_003", "The requested resource was not found.", 404)
    return user


@router.post("/{profile_user_id}/views", status_code=204)
def record_profile_view(profile_user_id: str, _user_id: str = CurrentUserId):
    store.record_profile_view(_user_id, profile_user_id)
    return Response(status_code=204)


@router.post("/{user_id}/like", status_code=204)
def like_profile(user_id: str, _user_id: str = CurrentUserId):
    store.like_profile(_user_id, user_id)
    return Response(status_code=204)


@router.delete("/{user_id}/like", status_code=204)
def unlike_profile(user_id: str, _user_id: str = CurrentUserId):
    store.unlike_profile(_user_id, user_id)
    return Response(status_code=204)


@router.get("/{user_id}/like")
def has_liked_profile(user_id: str, _user_id: str = CurrentUserId):
    return {"liked": store.has_liked_profile(_user_id, user_id)}


@router.post("/{user_id}/tap", status_code=204)
def tap_profile(user_id: str, _user_id: str = CurrentUserId):
    store.tap_profile(_user_id, user_id)
    return Response(status_code=204)


@router.get("/{user_id}/tap")
def has_tapped_profile(user_id: str, _user_id: str = CurrentUserId):
    return {"tapped": store.has_tapped_profile(_user_id, user_id)}


@router.get("/{user_id}/mutual-like")
def mutual_like(user_id: str, _user_id: str = CurrentUserId):
    return {"mutual": store.are_mutual_likes(_user_id, user_id)}


@router.get("/{user_id}/activity/summary")
def profile_activity_summary(user_id: str, _user_id: str = CurrentUserId):
    return store.get_profile_activity_summary(user_id)


@router.get("/{user_id}/activity/views")
def profile_views(user_id: str, _user_id: str = CurrentUserId):
    return store.get_profile_views(user_id)


@router.get("/{user_id}/activity/likes")
def profile_likes(user_id: str, _user_id: str = CurrentUserId):
    return store.get_profile_likes(user_id)


@router.get("/{user_id}/activity/taps")
def profile_taps(user_id: str, _user_id: str = CurrentUserId):
    return store.get_profile_taps(user_id)
