from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.auth import create_access_token, hash_password, verify_password
from app.errors import api_error
from app.geo import haversine_distance_meters
from app.models import (
    AppNotification,
    AuthSession,
    Conversation,
    CreateEventInput,
    CreateNotificationInput,
    Event,
    Message,
    PasswordResetRequestResult,
    PresignResponse,
    PresignUploadRequest,
    ProfileActivityItem,
    ProfileActivitySummary,
    RegisterInput,
    SocialLoginInput,
    TouchEvent,
    TrackTouchEventInput,
    UpdateEventInput,
    UpdateProfileInput,
    User,
    UserReport,
    UserSettings,
    new_id,
)
from app.seed import (
    CURRENT_USER_ID,
    build_seed_conversations,
    build_seed_events,
    build_seed_messages,
    build_seed_notifications,
    build_seed_users,
    default_settings,
    photo_seed,
)

MESSAGE_PAGE_SIZE = 20


@dataclass
class StoredAccount:
    email: str
    password_hash: str
    display_name: str
    age: int
    onboarded: bool = False


@dataclass
class ProfileView:
    id: str
    viewer_id: str
    profile_user_id: str
    viewed_at: str


@dataclass
class ProfileLike:
    id: str
    from_user_id: str
    to_user_id: str
    liked_at: str


class DataStore:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.users: dict[str, User] = {u.id: u for u in build_seed_users()}
        self.conversations: list[Conversation] = build_seed_conversations()
        self.messages: list[Message] = build_seed_messages(now)
        self.events: list[Event] = build_seed_events(now)
        self.notifications: list[AppNotification] = build_seed_notifications(now)
        self.settings: UserSettings = default_settings()
        self.accounts: dict[str, StoredAccount] = {}
        self.reset_codes: dict[str, tuple[str, datetime]] = {}
        self.email_codes: dict[str, tuple[str, datetime]] = {}
        self.rsvp_state: dict[str, list[str]] = {e.id: list(e.attendeeIds) for e in self.events}
        self.blocked_ids: set[str] = set()
        self.favorite_ids: set[str] = set()
        self.profile_views: list[ProfileView] = []
        self.profile_likes: list[ProfileLike] = []
        self.touch_events: list[TouchEvent] = []
        self.reports: list[UserReport] = []
        self.seen_event_ids: set[str] = set()
        self._seed_profile_activity(now)
        self._attach_last_messages()

    def _seed_profile_activity(self, now: datetime) -> None:
        for i, viewer_id in enumerate(["user-2", "user-3", "user-4", "user-5"], 1):
            self.profile_views.append(
                ProfileView(
                    id=f"view-{i}",
                    viewer_id=viewer_id,
                    profile_user_id=CURRENT_USER_ID,
                    viewed_at=(now - timedelta(minutes=i * 15)).isoformat(),
                )
            )
        for i, from_id in enumerate(["user-2", "user-4", "user-8"], 1):
            self.profile_likes.append(
                ProfileLike(
                    id=f"like-{i}",
                    from_user_id=from_id,
                    to_user_id=CURRENT_USER_ID,
                    liked_at=(now - timedelta(hours=i)).isoformat(),
                )
            )
        self.touch_events.append(
            TouchEvent(
                id="touch-1",
                type="profile_tap",
                actorUserId="user-3",
                targetUserId=CURRENT_USER_ID,
                screen="user_profile",
                createdAt=(now - timedelta(minutes=10)).isoformat(),
            )
        )

    def _attach_last_messages(self) -> None:
        for conv in self.conversations:
            msgs = [m for m in self.messages if m.conversationId == conv.id]
            if msgs:
                conv.lastMessage = msgs[-1]

    def _normalize_email(self, email: str) -> str:
        return email.strip().lower()

    def _get_me(self) -> User:
        user = self.users.get(CURRENT_USER_ID)
        if not user:
            raise api_error("RES_001", "User profile not found.", 404)
        return user

    def _apply_distance(self, user: User, origin_lat: float | None = None, origin_lng: float | None = None) -> User:
        me = self._get_me()
        lat = origin_lat if origin_lat is not None else me.latitude
        lng = origin_lng if origin_lng is not None else me.longitude
        data = user.model_copy()
        data.distanceMeters = haversine_distance_meters(lat, lng, user.latitude, user.longitude)
        return data

    def _to_list_user(self, user: User) -> User:
        data = user.model_copy()
        data.photos = user.photos[:1]
        data.albums = None
        return data

    def _sync_privacy(self) -> None:
        me = self._get_me()
        me.privacy.showOnMap = self.settings.showOnMap
        me.privacy.hideDistance = self.settings.hideDistance
        me.privacy.incognito = self.settings.incognito

    def _auth_session(self, onboarded: bool | None = None) -> AuthSession:
        me = self._apply_distance(self._get_me())
        ob = onboarded if onboarded is not None else self.settings.email in self.accounts and self.accounts[self.settings.email].onboarded
        token = create_access_token(CURRENT_USER_ID, self.settings.email)
        return AuthSession(token=token, user=me, onboarded=ob if ob is not None else True)

    def login(self, email: str, password: str) -> AuthSession:
        normalized = self._normalize_email(email)
        if normalized == "fail@example.com":
            raise api_error("AUTH_001", "Invalid email or password.", 401)
        if not password.strip():
            raise api_error("APP_002", "Please check your input and try again.", 400, "Password is required.")
        account = self.accounts.get(normalized)
        if account and not verify_password(password, account.password_hash):
            raise api_error("AUTH_001", "Invalid email or password.", 401)
        if account:
            me = self._get_me()
            me.displayName = account.display_name
            me.age = account.age
        self.settings.email = normalized
        return self._auth_session(onboarded=account.onboarded if account else False)

    def register(self, input: RegisterInput) -> AuthSession:
        normalized = self._normalize_email(input.email)
        if normalized == "fail@example.com":
            raise api_error("AUTH_001", "Invalid email or password.", 401)
        if normalized in self.accounts:
            raise api_error("API_007", "This action conflicts with existing data.", 409, "An account with this email already exists.")
        if input.age < 18:
            raise api_error("APP_002", "Please check your input and try again.", 400, "Age must be at least 18.")
        self.accounts[normalized] = StoredAccount(
            email=normalized,
            password_hash=hash_password(input.password),
            display_name=input.displayName.strip(),
            age=input.age,
            onboarded=False,
        )
        me = self._get_me()
        me.displayName = input.displayName.strip()
        me.age = input.age
        self.settings.email = normalized
        return self._auth_session(onboarded=False)

    def change_password(self, current_password: str, new_password: str) -> None:
        if current_password == new_password:
            raise api_error("APP_002", "Please check your input and try again.", 400, "New password must be different.")
        account = self.accounts.get(self.settings.email)
        if account:
            if not verify_password(current_password, account.password_hash):
                raise api_error("AUTH_001", "Invalid email or password.", 401, "Current password is incorrect.")
            account.password_hash = hash_password(new_password)
            return
        self.accounts[self.settings.email] = StoredAccount(
            email=self.settings.email,
            password_hash=hash_password(new_password),
            display_name=self._get_me().displayName,
            age=self._get_me().age,
            onboarded=True,
        )

    def delete_account(self) -> None:
        self.accounts.pop(self.settings.email, None)

    def request_password_reset(self, email: str) -> PasswordResetRequestResult:
        normalized = self._normalize_email(email)
        code = f"{random.randint(100000, 999999)}"
        self.reset_codes[normalized] = (code, datetime.now(timezone.utc) + timedelta(minutes=15))
        return PasswordResetRequestResult(sent=True, demoCode=code)

    def reset_password(self, email: str, code: str, new_password: str) -> None:
        normalized = self._normalize_email(email)
        pending = self.reset_codes.get(normalized)
        if not pending or pending[0] != code.strip() or pending[1] < datetime.now(timezone.utc):
            raise api_error("APP_002", "Please check your input and try again.", 400, "Reset code is invalid or expired.")
        account = self.accounts.get(normalized)
        if account:
            account.password_hash = hash_password(new_password)
        else:
            self.accounts[normalized] = StoredAccount(
                email=normalized,
                password_hash=hash_password(new_password),
                display_name="You",
                age=21,
                onboarded=True,
            )
        self.reset_codes.pop(normalized, None)

    def change_email(self, email: str) -> PasswordResetRequestResult:
        normalized = self._normalize_email(email)
        self.settings.email = normalized
        self.settings.emailVerified = False
        code = f"{random.randint(100000, 999999)}"
        self.email_codes[normalized] = (code, datetime.now(timezone.utc) + timedelta(minutes=15))
        return PasswordResetRequestResult(sent=True, demoCode=code)

    def verify_email(self, code: str) -> None:
        pending = self.email_codes.get(self.settings.email)
        if not pending or pending[0] != code.strip() or pending[1] < datetime.now(timezone.utc):
            raise api_error("APP_002", "Please check your input and try again.", 400, "Verification code is invalid or expired.")
        self.settings.emailVerified = True
        self.email_codes.pop(self.settings.email, None)

    def social_login(self, input: SocialLoginInput) -> AuthSession:
        email = self._normalize_email(input.email or f"{input.provider}.user@example.com")
        self.settings.email = email
        self.settings.emailVerified = True
        if input.displayName:
            self._get_me().displayName = input.displayName
        return self._auth_session(onboarded=True)

    def get_current_user(self) -> User:
        return self._apply_distance(self._get_me())

    def update_profile(self, partial: UpdateProfileInput) -> User:
        me = self._get_me()
        data = partial.model_dump(exclude_unset=True)
        if "photos" in data and data["photos"] is not None and len(data["photos"]) == 0:
            raise api_error("APP_002", "Please check your input and try again.", 400, "At least one photo is required.")
        for key, value in data.items():
            setattr(me, key, value)
        return self._apply_distance(me)

    def get_user(self, user_id: str) -> User | None:
        user = self.users.get(user_id)
        return self._apply_distance(user) if user else None

    def get_nearby_users(
        self,
        lat: float,
        lng: float,
        radius: float,
        online_only: bool,
        hosting_only: bool,
        age_min: int,
        age_max: int,
        sort: str,
    ) -> list[User]:
        results: list[User] = []
        now = datetime.now(timezone.utc)
        for user in self.users.values():
            if user.id == CURRENT_USER_ID or user.id in self.blocked_ids or user.privacy.incognito:
                continue
            with_distance = self._apply_distance(user, lat, lng)
            if (with_distance.distanceMeters or 0) > radius:
                continue
            if online_only and not user.isOnline:
                continue
            if hosting_only and not user.hostingTag:
                continue
            if user.age < age_min or user.age > age_max:
                continue
            results.append(with_distance)
        def boost_key(u: User) -> int:
            if u.boostedUntil and datetime.fromisoformat(u.boostedUntil.replace("Z", "+00:00")) > now:
                return 1
            return 0
        if sort == "distance":
            results.sort(key=lambda u: (boost_key(u), u.distanceMeters or 0), reverse=True)
        elif sort == "lastActive":
            results.sort(key=lambda u: (boost_key(u), u.lastActiveAt), reverse=True)
        else:
            results.sort(key=lambda u: (boost_key(u), u.id))
        return [self._to_list_user(u) for u in results]

    def request_verification(self) -> User:
        me = self._get_me()
        me.verified = True
        return self._apply_distance(me)

    def boost_profile(self) -> User:
        me = self._get_me()
        me.boostedUntil = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        me.premium = True
        self.settings.premium = True
        return self._apply_distance(me)

    def get_settings(self) -> UserSettings:
        return self.settings.model_copy()

    def update_settings(self, partial: dict) -> UserSettings:
        for key, value in partial.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
        if any(k in partial for k in ("showOnMap", "hideDistance", "incognito")):
            self._sync_privacy()
        return self.settings.model_copy()

    def set_premium(self, enabled: bool) -> UserSettings:
        self.settings.premium = enabled
        self._get_me().premium = enabled
        return self.settings.model_copy()

    def get_conversations(self) -> list[Conversation]:
        result = []
        for conv in self.conversations:
            if conv.isGroup:
                result.append(conv.model_copy())
                continue
            other = next((pid for pid in conv.participantIds if pid != CURRENT_USER_ID), None)
            if other and other not in self.blocked_ids:
                result.append(conv.model_copy())
        return result

    def create_conversation(self, participant_id: str) -> Conversation:
        if self.settings.requireMutualMatch and not self.are_mutual_likes(CURRENT_USER_ID, participant_id):
            raise api_error("API_006", "You do not have permission for this action.", 403, "Like each other to chat")
        for conv in self.conversations:
            if not conv.isGroup and set(conv.participantIds) == {CURRENT_USER_ID, participant_id}:
                return conv.model_copy()
        conv = Conversation(id=new_id("conv"), participantIds=[CURRENT_USER_ID, participant_id], unreadCount=0)
        self.conversations.insert(0, conv)
        return conv.model_copy()

    def create_group_conversation(self, participant_ids: list[str], title: str) -> Conversation:
        unique = list(dict.fromkeys(pid for pid in participant_ids if pid and pid != CURRENT_USER_ID))
        conv = Conversation(
            id=new_id("conv"),
            participantIds=[CURRENT_USER_ID, *unique],
            unreadCount=0,
            isGroup=True,
            title=title.strip() or "Group",
        )
        self.conversations.insert(0, conv)
        return conv.model_copy()

    def get_messages(self, conversation_id: str, cursor: str | None, limit: int) -> list[Message]:
        all_msgs = sorted(
            [m for m in self.messages if m.conversationId == conversation_id],
            key=lambda m: m.createdAt,
        )
        page_size = limit or MESSAGE_PAGE_SIZE
        if not cursor:
            return [m.model_copy() for m in all_msgs[-page_size:]]
        index = next((i for i, m in enumerate(all_msgs) if m.id == cursor), -1)
        if index <= 0:
            return []
        start = max(0, index - page_size)
        return [m.model_copy() for m in all_msgs[start:index]]

    def add_message(self, message: Message) -> Message:
        self.messages.append(message)
        conv = next((c for c in self.conversations if c.id == message.conversationId), None)
        if conv:
            conv.lastMessage = message
            if message.senderId != CURRENT_USER_ID:
                conv.unreadCount += 1
        return message

    def mark_conversation_read(self, conversation_id: str) -> None:
        conv = next((c for c in self.conversations if c.id == conversation_id), None)
        if conv:
            conv.unreadCount = 0
        for msg in self.messages:
            if msg.conversationId == conversation_id and msg.status != "failed":
                msg.status = "read"

    def edit_message(self, message_id: str, body: str) -> Message | None:
        msg = next((m for m in self.messages if m.id == message_id and m.senderId == CURRENT_USER_ID), None)
        if not msg or msg.deletedAt:
            return msg.model_copy() if msg else None
        msg.body = body.strip()
        msg.editedAt = datetime.now(timezone.utc).isoformat()
        return msg.model_copy()

    def delete_message(self, message_id: str) -> Message | None:
        msg = next((m for m in self.messages if m.id == message_id and m.senderId == CURRENT_USER_ID), None)
        if not msg:
            return None
        msg.body = ""
        msg.deletedAt = datetime.now(timezone.utc).isoformat()
        msg.mediaUrl = None
        msg.thumbnailUrl = None
        return msg.model_copy()

    def mark_message_viewed(self, message_id: str, viewed_at: str) -> Message | None:
        msg = next((m for m in self.messages if m.id == message_id), None)
        if not msg or not msg.viewOnce or msg.viewedAt:
            return msg.model_copy() if msg else None
        msg.viewedAt = viewed_at
        msg.mediaUrl = None
        msg.thumbnailUrl = None
        conv = next((c for c in self.conversations if c.id == msg.conversationId), None)
        if conv and conv.lastMessage and conv.lastMessage.id == message_id:
            conv.lastMessage = msg.model_copy()
        return msg.model_copy()

    def get_events(self, filter_name: str | None, origin_lat: float, origin_lng: float) -> list[Event]:
        now = datetime.now(timezone.utc)
        result = []
        for event in self.events:
            data = event.model_copy()
            data.attendeeIds = self.rsvp_state.get(event.id, event.attendeeIds)
            start = datetime.fromisoformat(data.startsAt.replace("Z", "+00:00"))
            if filter_name == "today" and not (now - timedelta(days=1) < start < now + timedelta(days=1)):
                continue
            if filter_name == "week" and not (now - timedelta(days=1) < start < now + timedelta(days=7)):
                continue
            if filter_name == "hosting" and data.hostId != CURRENT_USER_ID:
                continue
            data.distanceMeters = haversine_distance_meters(origin_lat, origin_lng, data.latitude, data.longitude)
            result.append(data)
        return result

    def get_event(self, event_id: str) -> Event | None:
        event = next((e for e in self.events if e.id == event_id), None)
        if not event:
            return None
        data = event.model_copy()
        data.attendeeIds = self.rsvp_state.get(event_id, event.attendeeIds)
        return data

    def create_event(self, input: CreateEventInput, origin_lat: float, origin_lng: float) -> Event:
        event = Event(
            id=new_id("event"),
            title=input.title.strip(),
            description=input.description.strip(),
            startsAt=input.startsAt,
            venueName=input.venueName.strip(),
            latitude=input.latitude if input.latitude is not None else origin_lat + (random.random() - 0.5) * 0.012,
            longitude=input.longitude if input.longitude is not None else origin_lng + (random.random() - 0.5) * 0.012,
            hostId=CURRENT_USER_ID,
            attendeeIds=[CURRENT_USER_ID],
            coverImageUrl=input.coverImageUrl or photo_seed(new_id("cover")),
        )
        self.events.insert(0, event)
        self.rsvp_state[event.id] = [CURRENT_USER_ID]
        return event.model_copy()

    def update_event(self, event_id: str, input: UpdateEventInput) -> Event | None:
        event = next((e for e in self.events if e.id == event_id and e.hostId == CURRENT_USER_ID), None)
        if not event:
            return None
        for key, value in input.model_dump(exclude_unset=True).items():
            setattr(event, key, value)
        return self.get_event(event_id)

    def delete_event(self, event_id: str) -> None:
        index = next((i for i, e in enumerate(self.events) if e.id == event_id and e.hostId == CURRENT_USER_ID), -1)
        if index >= 0:
            self.events.pop(index)
            self.rsvp_state.pop(event_id, None)

    def rsvp_event(self, event_id: str) -> Event | None:
        attendees = self.rsvp_state.setdefault(event_id, [])
        if CURRENT_USER_ID not in attendees:
            attendees.append(CURRENT_USER_ID)
        return self.get_event(event_id)

    def cancel_rsvp(self, event_id: str) -> Event | None:
        event = self.get_event(event_id)
        if event and event.hostId == CURRENT_USER_ID:
            return event
        self.rsvp_state[event_id] = [uid for uid in self.rsvp_state.get(event_id, []) if uid != CURRENT_USER_ID]
        return self.get_event(event_id)

    def get_event_attendees(self, event_id: str) -> list[User]:
        event = self.get_event(event_id)
        if not event:
            return []
        return [self._to_list_user(self._apply_distance(self.users[uid])) for uid in event.attendeeIds if uid in self.users]

    def notify_new_nearby_events(self, origin_lat: float, origin_lng: float) -> int:
        count = 0
        for event in self.get_events(None, origin_lat, origin_lng):
            if event.id in self.seen_event_ids:
                continue
            self.seen_event_ids.add(event.id)
            self.notifications.insert(
                0,
                AppNotification(
                    id=new_id("notif"),
                    type="event",
                    title=f"New event: {event.title}",
                    body=f"{event.venueName} · nearby",
                    createdAt=datetime.now(timezone.utc).isoformat(),
                    read=False,
                    eventId=event.id,
                ),
            )
            count += 1
        return count

    def track_touch_event(self, input: TrackTouchEventInput) -> TouchEvent:
        event = TouchEvent(
            id=new_id("touch"),
            type=input.type,
            actorUserId=input.actorUserId,
            targetUserId=input.targetUserId,
            screen=input.screen,
            createdAt=datetime.now(timezone.utc).isoformat(),
            metadata=input.metadata,
        )
        self.touch_events.append(event)
        return event

    def record_profile_view(self, viewer_id: str, profile_user_id: str) -> None:
        if viewer_id == profile_user_id:
            return
        self.profile_views.append(
            ProfileView(
                id=new_id("view"),
                viewer_id=viewer_id,
                profile_user_id=profile_user_id,
                viewed_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        self.track_touch_event(
            TrackTouchEventInput(
                type="profile_view",
                actorUserId=viewer_id,
                targetUserId=profile_user_id,
                screen="user_profile",
            )
        )

    def like_profile(self, from_user_id: str, to_user_id: str) -> None:
        if from_user_id == to_user_id:
            return
        if any(l.from_user_id == from_user_id and l.to_user_id == to_user_id for l in self.profile_likes):
            return
        self.profile_likes.append(
            ProfileLike(id=new_id("like"), from_user_id=from_user_id, to_user_id=to_user_id, liked_at=datetime.now(timezone.utc).isoformat())
        )
        self.track_touch_event(
            TrackTouchEventInput(type="profile_like", actorUserId=from_user_id, targetUserId=to_user_id, screen="user_profile")
        )

    def unlike_profile(self, from_user_id: str, to_user_id: str) -> None:
        self.profile_likes = [l for l in self.profile_likes if not (l.from_user_id == from_user_id and l.to_user_id == to_user_id)]
        self.track_touch_event(
            TrackTouchEventInput(type="profile_unlike", actorUserId=from_user_id, targetUserId=to_user_id, screen="user_profile")
        )

    def tap_profile(self, from_user_id: str, to_user_id: str) -> None:
        if from_user_id == to_user_id:
            return
        self.track_touch_event(
            TrackTouchEventInput(type="profile_tap", actorUserId=from_user_id, targetUserId=to_user_id, screen="user_profile")
        )

    def has_liked_profile(self, from_user_id: str, to_user_id: str) -> bool:
        return any(l.from_user_id == from_user_id and l.to_user_id == to_user_id for l in self.profile_likes)

    def has_tapped_profile(self, from_user_id: str, to_user_id: str) -> bool:
        return any(
            e.type == "profile_tap" and e.actorUserId == from_user_id and e.targetUserId == to_user_id
            for e in self.touch_events
        )

    def are_mutual_likes(self, user_a: str, user_b: str) -> bool:
        return self.has_liked_profile(user_a, user_b) and self.has_liked_profile(user_b, user_a)

    def get_favorite_users(self) -> list[User]:
        return [
            self._to_list_user(self._apply_distance(self.users[uid]))
            for uid in self.favorite_ids
            if uid in self.users and uid not in self.blocked_ids
        ]

    def is_favorite(self, user_id: str) -> bool:
        return user_id in self.favorite_ids

    def add_favorite(self, user_id: str) -> None:
        if user_id and user_id != CURRENT_USER_ID:
            self.favorite_ids.add(user_id)

    def remove_favorite(self, user_id: str) -> None:
        self.favorite_ids.discard(user_id)

    def get_profile_activity_summary(self, user_id: str) -> ProfileActivitySummary:
        views = [v for v in self.profile_views if v.profile_user_id == user_id]
        likes = [l for l in self.profile_likes if l.to_user_id == user_id]
        taps = [e for e in self.touch_events if e.type == "profile_tap" and e.targetUserId == user_id]
        return ProfileActivitySummary(
            viewsCount=len({v.viewer_id for v in views}),
            likesCount=len(likes),
            tapsCount=len({e.actorUserId for e in taps}),
        )

    def _activity_items(self, user_ids_with_at: list[tuple[str, str]]) -> list[ProfileActivityItem]:
        items = []
        for user_id, at in user_ids_with_at:
            user = self.users.get(user_id)
            if user and user_id not in self.blocked_ids:
                items.append(ProfileActivityItem(user=self._to_list_user(self._apply_distance(user)), at=at))
        return sorted(items, key=lambda i: i.at, reverse=True)

    def get_profile_views(self, user_id: str) -> list[ProfileActivityItem]:
        latest: dict[str, str] = {}
        for view in self.profile_views:
            if view.profile_user_id != user_id:
                continue
            if view.viewer_id not in latest or view.viewed_at > latest[view.viewer_id]:
                latest[view.viewer_id] = view.viewed_at
        return self._activity_items(list(latest.items()))

    def get_profile_likes(self, user_id: str) -> list[ProfileActivityItem]:
        return self._activity_items([(l.from_user_id, l.liked_at) for l in self.profile_likes if l.to_user_id == user_id])

    def get_profile_taps(self, user_id: str) -> list[ProfileActivityItem]:
        latest: dict[str, str] = {}
        for tap in self.touch_events:
            if tap.type != "profile_tap" or tap.targetUserId != user_id or not tap.actorUserId:
                continue
            if tap.actorUserId not in latest or tap.createdAt > latest[tap.actorUserId]:
                latest[tap.actorUserId] = tap.createdAt
        return self._activity_items(list(latest.items()))

    def get_blocked_ids(self) -> list[str]:
        return list(self.blocked_ids)

    def get_blocked_users(self) -> list[User]:
        return [self._to_list_user(self._apply_distance(self.users[uid])) for uid in self.blocked_ids if uid in self.users]

    def block_user(self, user_id: str) -> None:
        if user_id and user_id != CURRENT_USER_ID:
            self.blocked_ids.add(user_id)

    def unblock_user(self, user_id: str) -> None:
        self.blocked_ids.discard(user_id)

    def report_user(self, user_id: str, reason: str, conversation_id: str | None, details: str | None) -> UserReport:
        report = UserReport(
            id=new_id("report"),
            reportedUserId=user_id,
            conversationId=conversation_id,
            reason=reason,
            details=details,
            createdAt=datetime.now(timezone.utc).isoformat(),
            status="submitted",
        )
        self.reports.append(report)
        return report

    def get_reports(self) -> list[UserReport]:
        return [r.model_copy() for r in self.reports]

    def get_notifications(self) -> list[AppNotification]:
        return sorted([n.model_copy() for n in self.notifications], key=lambda n: n.createdAt, reverse=True)

    def get_unread_notification_count(self) -> int:
        return sum(1 for n in self.notifications if not n.read)

    def create_notification(self, input: CreateNotificationInput) -> AppNotification:
        item = AppNotification(
            id=new_id("notif"),
            type=input.type,
            title=input.title,
            body=input.body,
            createdAt=datetime.now(timezone.utc).isoformat(),
            read=False,
            userId=input.userId,
            conversationId=input.conversationId,
            eventId=input.eventId,
        )
        self.notifications.insert(0, item)
        return item

    def mark_notification_read(self, notification_id: str) -> None:
        item = next((n for n in self.notifications if n.id == notification_id), None)
        if item:
            item.read = True

    def mark_all_notifications_read(self) -> None:
        for item in self.notifications:
            item.read = True

    def scan_media(self, file_name: str) -> dict:
        lowered = file_name.lower()
        if "illegal" in lowered or "csam" in lowered:
            return {"ok": False, "reason": "This file was blocked by the safety filter."}
        return {"ok": True}

    def create_presigned_upload(self, request: PresignUploadRequest, user_id: str) -> PresignResponse:
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", request.fileName)[:80] or "media"
        folder = re.sub(r"[^a-zA-Z0-9/_-]", "", request.folder or "albums") or "albums"
        key = f"{folder}/{user_id}/{int(datetime.now(timezone.utc).timestamp() * 1000)}-{safe_name}"
        return PresignResponse(
            key=key,
            uploadUrl=f"mock://s3/{key}",
            publicUrl="",
            headers={"Content-Type": request.contentType},
            expiresInSeconds=900,
            mode="mock",
        )

    def conversation_participant_ids(self, conversation_id: str) -> list[str]:
        conv = next((c for c in self.conversations if c.id == conversation_id), None)
        return conv.participantIds if conv else []

    def find_message_by_client_id(self, client_id: str) -> Message | None:
        return next((m for m in self.messages if m.clientId == client_id), None)


store = DataStore()
