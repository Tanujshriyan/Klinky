from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.auth import create_access_token, create_admin_token, hash_password, verify_password
from app.config import settings
from app.errors import api_error
from app.geo import haversine_distance_meters
from app.geohash import decode_geohash
from app.models import (
    AdminAuditLogEntry,
    AdminSession,
    AdminUserSummary,
    AppNotification,
    AuthSession,
    ConsentRecord,
    ContentModerationItem,
    Conversation,
    CreateEventInput,
    CreateNotificationInput,
    DataExportRequest,
    Event,
    Message,
    PasswordResetRequestResult,
    PhotoAlbum,
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
ADMIN_USER_ID = "admin-system"
MAX_FILENAME_LENGTH = 255
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_VIDEO_MIMES = {"video/mp4", "video/quicktime", "video/x-m4v"}
MIN_PASSWORD_LENGTH = 8
AUDIT_LOG_MAX_ENTRIES = 500


def _age_from_birth_date(birth_date: str) -> int:
    parts = birth_date.split("-")
    if len(parts) != 3:
        raise ValueError("Invalid birth date format.")
    year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    today = datetime.now(timezone.utc).date()
    age = today.year - year
    if (today.month, today.day) < (month, day):
        age -= 1
    return age


@dataclass
class StoredAccount:
    email: str
    password_hash: str
    display_name: str
    age: int
    birth_date: str | None = None
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
        self.blocked_by_ids: set[str] = set()
        self.favorite_ids: set[str] = set()
        self.profile_views: list[ProfileView] = []
        self.profile_likes: list[ProfileLike] = []
        self.touch_events: list[TouchEvent] = []
        self.reports: list[UserReport] = []
        self.user_status: dict[str, str] = {}
        self.user_suspended_until: dict[str, str] = {}
        self.user_banned_at: dict[str, str] = {}
        self.user_moderation_reasons: dict[str, str] = {}
        self.content_items: list[ContentModerationItem] = []
        self.audit_logs: list[AdminAuditLogEntry] = []
        self.user_consents: dict[str, list[ConsentRecord]] = {}
        self.data_export_requests: list[DataExportRequest] = []
        self.user_audit_logs: list[dict] = []
        self.seen_event_ids: set[str] = set()
        self._seed_sample_report(now)
        self._seed_profile_activity(now)
        self._attach_last_messages()

    def _seed_sample_report(self, now: datetime) -> None:
        """Seed one report so admin moderation screens have demo data."""
        report = UserReport(
            id="report-seed-1",
            reportedUserId="user-5",
            reporterUserId="user-2",
            reason="inappropriate",
            details="Profile photos look suspicious.",
            createdAt=(now - timedelta(hours=2)).isoformat(),
            status="submitted",
        )
        self.reports.append(report)
        self._ensure_content_flag_for_report(report)

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

    def _validate_password(self, password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise api_error(
                "APP_002",
                "Please check your input and try again.",
                400,
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            )

    def _password_reset_result(self, sent: bool, demo_code: str | None = None) -> PasswordResetRequestResult:
        if settings.dev_mode:
            return PasswordResetRequestResult(sent=sent, demoCode=demo_code)
        return PasswordResetRequestResult(sent=sent)

    def _get_user_status(self, user_id: str) -> str:
        until = self.user_suspended_until.get(user_id)
        if until:
            expires = datetime.fromisoformat(until.replace("Z", "+00:00"))
            if expires <= datetime.now(timezone.utc):
                self.user_status.pop(user_id, None)
                self.user_suspended_until.pop(user_id, None)
                return "active"
        return self.user_status.get(user_id, "active")

    def _lookup_user_email(self, user_id: str) -> str | None:
        for email, account in self.accounts.items():
            if user_id == CURRENT_USER_ID and email == self.settings.email:
                return email
        return None

    def _report_count_for_user(self, user_id: str) -> int:
        return sum(1 for r in self.reports if r.reportedUserId == user_id and r.status in ("submitted", "reviewing"))

    def _log_user_event(self, action: str, details: dict | None = None) -> None:
        entry = {
            "id": new_id("ual"),
            "userId": CURRENT_USER_ID,
            "action": action,
            "details": details,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        self.user_audit_logs.insert(0, entry)
        if len(self.user_audit_logs) > USER_AUDIT_LOG_CAP:
            self.user_audit_logs = self.user_audit_logs[:USER_AUDIT_LOG_CAP]

    def _log_admin_action(
        self,
        admin_id: str,
        admin_email: str,
        action: str,
        target_type: str,
        target_id: str,
        details: dict | None = None,
        ip_address: str | None = None,
    ) -> AdminAuditLogEntry:
        entry = AdminAuditLogEntry(
            id=new_id("audit"),
            adminId=admin_id,
            adminEmail=admin_email,
            action=action,
            targetType=target_type,
            targetId=target_id,
            details=details,
            createdAt=datetime.now(timezone.utc).isoformat(),
            ipAddress=ip_address,
        )
        self.audit_logs.insert(0, entry)
        if len(self.audit_logs) > AUDIT_LOG_MAX_ENTRIES:
            self.audit_logs = self.audit_logs[:AUDIT_LOG_MAX_ENTRIES]
        return entry

    def _ensure_content_flag_for_report(self, report: UserReport) -> None:
        user = self.users.get(report.reportedUserId)
        if not user:
            return
        content_id = f"profile-{report.reportedUserId}"
        if any(item.id == content_id and item.status == "pending" for item in self.content_items):
            return
        self.content_items.insert(
            0,
            ContentModerationItem(
                id=content_id,
                contentType="profile",
                userId=report.reportedUserId,
                userDisplayName=user.displayName,
                photoUrl=user.photos[0] if user.photos else None,
                status="pending",
                reportId=report.id,
                reason=report.reason,
                createdAt=report.createdAt,
            ),
        )
        for index, photo_url in enumerate(user.photos):
            photo_id = f"photo-{report.reportedUserId}-{index}"
            if any(item.id == photo_id for item in self.content_items):
                continue
            self.content_items.append(
                ContentModerationItem(
                    id=photo_id,
                    contentType="photo",
                    userId=report.reportedUserId,
                    userDisplayName=user.displayName,
                    photoUrl=photo_url,
                    status="pending",
                    reportId=report.id,
                    reason=report.reason,
                    createdAt=report.createdAt,
                )
            )

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
        return self._redact_for_viewer(data, False)

    def _profile_visibility(self, user: User) -> str:
        if user.privacy.profileVisibility:
            return user.privacy.profileVisibility
        return "hidden" if user.privacy.incognito else "everyone"

    def _visible_in_discovery(self, user: User, *, for_nearby: bool = False) -> bool:
        if self._get_user_status(user.id) in ("suspended", "banned"):
            return False
        visibility = self._profile_visibility(user)
        if visibility == "hidden" or user.privacy.incognito:
            return False
        if for_nearby:
            return visibility in ("nearby", "everyone")
        return visibility == "everyone"

    def _is_blocked_either_way(self, user_id: str) -> bool:
        return user_id in self.blocked_ids or user_id in self.blocked_by_ids

    def _raise_if_blocked(self, user_id: str) -> None:
        if self._is_blocked_either_way(user_id):
            raise api_error(
                "API_006",
                "You do not have permission for this action.",
                403,
                "This user is blocked.",
            )

    def _conversation_has_block(self, conversation_id: str) -> bool:
        for participant_id in self.conversation_participant_ids(conversation_id):
            if participant_id != CURRENT_USER_ID and self._is_blocked_either_way(participant_id):
                return True
        return False

    def _redact_albums_for_viewer(self, albums: list[PhotoAlbum] | None, viewer_is_owner: bool) -> list[PhotoAlbum] | None:
        if not albums or viewer_is_owner:
            return albums
        redacted: list[PhotoAlbum] = []
        for album in albums:
            copy = album.model_copy()
            if album.nsfw:
                copy.items = []
                copy.locked = True
            redacted.append(copy)
        return redacted

    def _redact_for_viewer(self, user: User, viewer_is_owner: bool) -> User:
        data = user.model_copy()
        if viewer_is_owner:
            return data
        if user.privacy.showOnlineStatus is False:
            data.isOnline = False
        if user.privacy.shareApproximateLocation is False:
            data.latitude = 0.0
            data.longitude = 0.0
            data.distanceMeters = None
        else:
            centroid = decode_geohash(user.geohash)
            data.latitude = centroid["latitude"]
            data.longitude = centroid["longitude"]
            if user.privacy.hideDistance:
                data.distanceMeters = None
        if data.albums is not None:
            data.albums = self._redact_albums_for_viewer(data.albums, False)
        return data

    def _sync_privacy(self) -> None:
        me = self._get_me()
        me.privacy.showOnMap = self.settings.showOnMap
        me.privacy.hideDistance = self.settings.hideDistance
        me.privacy.incognito = self.settings.incognito
        me.privacy.profileVisibility = self.settings.profileVisibility
        me.privacy.shareApproximateLocation = self.settings.shareApproximateLocation
        me.privacy.showOnlineStatus = self.settings.showOnlineStatus

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
        if not account or not verify_password(password, account.password_hash):
            raise api_error("AUTH_001", "Invalid email or password.", 401)
        status = self._get_user_status(CURRENT_USER_ID)
        if status == "banned":
            raise api_error("API_006", "You do not have permission for this action.", 403, "This account has been banned.")
        if status == "suspended":
            raise api_error("API_006", "You do not have permission for this action.", 403, "This account is suspended.")
        me = self._get_me()
        me.displayName = account.display_name
        me.age = account.age
        if account.birth_date:
            me.birthDate = account.birth_date
        self.settings.email = normalized
        self._log_user_event("login", {"email": normalized})
        return self._auth_session(onboarded=account.onboarded)

    def register(self, input: RegisterInput) -> AuthSession:
        normalized = self._normalize_email(input.email)
        if normalized == "fail@example.com":
            raise api_error("AUTH_001", "Invalid email or password.", 401)
        if normalized in self.accounts:
            raise api_error("API_007", "This action conflicts with existing data.", 409, "An account with this email already exists.")
        age = input.age
        birth_date = input.birthDate
        if birth_date:
            try:
                age = _age_from_birth_date(birth_date)
            except ValueError:
                raise api_error("APP_002", "Please check your input and try again.", 400, "Invalid birth date.")
        if age < 18:
            raise api_error("APP_002", "Please check your input and try again.", 400, "Age must be at least 18.")
        self._validate_password(input.password)
        self.accounts[normalized] = StoredAccount(
            email=normalized,
            password_hash=hash_password(input.password),
            display_name=input.displayName.strip(),
            age=age,
            birth_date=birth_date,
            onboarded=False,
        )
        me = self._get_me()
        me.displayName = input.displayName.strip()
        me.age = age
        me.birthDate = birth_date
        self.settings.email = normalized
        self._log_user_event("register", {"email": normalized})
        return self._auth_session(onboarded=False)

    def change_password(self, current_password: str, new_password: str) -> None:
        if current_password == new_password:
            raise api_error("APP_002", "Please check your input and try again.", 400, "New password must be different.")
        self._validate_password(new_password)
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
        user_id = CURRENT_USER_ID
        self._log_user_event("delete", {"userId": user_id})

        conv_ids = {c.id for c in self.conversations if user_id in c.participantIds}
        self.messages = [
            m for m in self.messages if m.conversationId not in conv_ids and m.senderId != user_id
        ]
        self.conversations = [c for c in self.conversations if user_id not in c.participantIds]

        me = self._get_me()
        me.displayName = "Deleted User"
        me.bio = None
        me.photos = []
        me.albums = None
        me.tags = None
        me.kinks = None
        me.stats = None
        me.hostingTag = None
        me.birthDate = None
        me.verified = False
        me.premium = False
        me.boostedUntil = None

        self.favorite_ids = {fid for fid in self.favorite_ids if fid != user_id}
        self.blocked_ids = {bid for bid in self.blocked_ids if bid != user_id}
        self.profile_views = [
            v for v in self.profile_views if v.viewer_id != user_id and v.profile_user_id != user_id
        ]
        self.profile_likes = [
            l for l in self.profile_likes if l.from_user_id != user_id and l.to_user_id != user_id
        ]
        self.touch_events = [
            e
            for e in self.touch_events
            if e.actorUserId != user_id and e.targetUserId != user_id
        ]
        self.notifications = [n for n in self.notifications if n.userId != user_id]

        for report in self.reports:
            if report.reporterUserId == user_id:
                report.reporterUserId = None
            if report.reportedUserId == user_id:
                report.reportedUserId = "deleted-user"
                if report.details:
                    report.details = "[Account deleted]"

        self.user_consents.pop(user_id, None)
        self.accounts.pop(self.settings.email, None)

    def request_password_reset(self, email: str) -> PasswordResetRequestResult:
        normalized = self._normalize_email(email)
        code = f"{random.randint(100000, 999999)}"
        self.reset_codes[normalized] = (code, datetime.now(timezone.utc) + timedelta(minutes=15))
        return self._password_reset_result(sent=True, demo_code=code)

    def reset_password(self, email: str, code: str, new_password: str) -> None:
        normalized = self._normalize_email(email)
        pending = self.reset_codes.get(normalized)
        if not pending or pending[0] != code.strip() or pending[1] < datetime.now(timezone.utc):
            raise api_error("APP_002", "Please check your input and try again.", 400, "Reset code is invalid or expired.")
        self._validate_password(new_password)
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
        return self._password_reset_result(sent=True, demo_code=code)

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
        account = self.accounts.get(email)
        if account:
            account.onboarded = False
        self._log_user_event("login", {"email": email, "provider": input.provider})
        return self._auth_session(onboarded=False)

    def get_current_user(self) -> User:
        return self._apply_distance(self._get_me())

    def update_profile(self, partial: UpdateProfileInput) -> User:
        me = self._get_me()
        data = partial.model_dump(exclude_unset=True)
        if "photos" in data and data["photos"] is not None and len(data["photos"]) == 0:
            raise api_error("APP_002", "Please check your input and try again.", 400, "At least one photo is required.")
        geohash = data.pop("geohash", None)
        if geohash:
            coords = decode_geohash(geohash)
            me.geohash = geohash
            me.latitude = coords["latitude"]
            me.longitude = coords["longitude"]
        for key, value in data.items():
            setattr(me, key, value)
        return self._apply_distance(me)

    def get_user(self, user_id: str) -> User | None:
        user = self.users.get(user_id)
        if not user:
            return None
        result = self._apply_distance(user)
        return self._redact_for_viewer(result, user_id == CURRENT_USER_ID)

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
            if user.id == CURRENT_USER_ID or self._is_blocked_either_way(user.id):
                continue
            if not self._visible_in_discovery(user, for_nearby=True):
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
        if "profileVisibility" in partial:
            self.settings.incognito = partial["profileVisibility"] == "hidden"
        if any(
            k in partial
            for k in (
                "showOnMap",
                "hideDistance",
                "incognito",
                "profileVisibility",
                "shareApproximateLocation",
                "showOnlineStatus",
            )
        ):
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
            if other and not self._is_blocked_either_way(other):
                result.append(conv.model_copy())
        return result

    def create_conversation(self, participant_id: str) -> Conversation:
        self._raise_if_blocked(participant_id)
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
        if self._conversation_has_block(message.conversationId):
            raise api_error(
                "API_006",
                "You do not have permission for this action.",
                403,
                "This user is blocked.",
            )
        self.messages.append(message)
        _trim_conversation_messages(self.messages, message.conversationId)
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
            _cap_mutable_list(self.notifications, MAX_NOTIFICATIONS)
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
        if viewer_id == CURRENT_USER_ID:
            self._raise_if_blocked(profile_user_id)
        elif profile_user_id == CURRENT_USER_ID:
            self._raise_if_blocked(viewer_id)
        self.profile_views.append(
            ProfileView(
                id=new_id("view"),
                viewer_id=viewer_id,
                profile_user_id=profile_user_id,
                viewed_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        _cap_mutable_list(self.profile_views, MAX_PROFILE_VIEWS)
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
        if from_user_id == CURRENT_USER_ID:
            self._raise_if_blocked(to_user_id)
        elif to_user_id == CURRENT_USER_ID:
            self._raise_if_blocked(from_user_id)
        if any(l.from_user_id == from_user_id and l.to_user_id == to_user_id for l in self.profile_likes):
            return
        self.profile_likes.append(
            ProfileLike(id=new_id("like"), from_user_id=from_user_id, to_user_id=to_user_id, liked_at=datetime.now(timezone.utc).isoformat())
        )
        _cap_mutable_list(self.profile_likes, MAX_PROFILE_LIKES)
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
        if from_user_id == CURRENT_USER_ID:
            self._raise_if_blocked(to_user_id)
        elif to_user_id == CURRENT_USER_ID:
            self._raise_if_blocked(from_user_id)
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
            self._log_user_event("block", {"blockedUserId": user_id})

    def unblock_user(self, user_id: str) -> None:
        self.blocked_ids.discard(user_id)

    def report_user(
        self,
        user_id: str,
        reason: str,
        conversation_id: str | None,
        details: str | None,
        reporter_user_id: str | None = None,
    ) -> UserReport:
        valid_reasons = {"spam", "harassment", "inappropriate", "fake", "underage", "other"}
        if reason not in valid_reasons:
            raise api_error("APP_002", "Please check your input and try again.", 400, "Invalid report reason.")
        if details is not None and len(details) > 500:
            raise api_error("APP_002", "Please check your input and try again.", 400, "Details must be at most 500 characters.")
        if user_id not in self.users:
            raise api_error("API_003", "The requested resource was not found.", 404, "Reported user not found.")
        report = UserReport(
            id=new_id("report"),
            reportedUserId=user_id,
            reporterUserId=reporter_user_id,
            conversationId=conversation_id,
            reason=reason,
            details=details,
            createdAt=datetime.now(timezone.utc).isoformat(),
            status="submitted",
        )
        self.reports.append(report)
        _cap_mutable_list(self.reports, MAX_REPORTS)
        self._ensure_content_flag_for_report(report)
        self._log_user_event("report", {"reportedUserId": user_id, "reason": reason})
        return report

    def record_consent(self, consent_type: str, version: str) -> ConsentRecord:
        record = ConsentRecord(
            type=consent_type,
            version=version,
            acceptedAt=datetime.now(timezone.utc).isoformat(),
        )
        consents = self.user_consents.setdefault(CURRENT_USER_ID, [])
        consents.append(record)
        self._log_user_event("consent", {"type": consent_type, "version": version})
        return record

    def request_data_export(self) -> dict:
        request = DataExportRequest(
            id=new_id("export"),
            userId=CURRENT_USER_ID,
            status="pending",
            requestedAt=datetime.now(timezone.utc).isoformat(),
        )
        self.data_export_requests.insert(0, request)
        self._log_user_event("export", {"requestId": request.id})
        return {"requestId": request.id, "status": request.status}

    def get_data_export_status(self, request_id: str) -> DataExportRequest:
        export = next(
            (
                item
                for item in self.data_export_requests
                if item.id == request_id and item.userId == CURRENT_USER_ID
            ),
            None,
        )
        if not export:
            raise api_error("API_003", "The requested resource was not found.", 404, "Export request not found.")
        return export.model_copy()

    def get_reports(self, reporter_user_id: str | None = None) -> list[UserReport]:
        reports = self.reports
        if reporter_user_id is not None:
            reports = [r for r in reports if r.reporterUserId == reporter_user_id]
        return [r.model_copy() for r in reports]

    # --- Admin moderation ---

    def admin_login(self, email: str, password: str, ip_address: str | None = None) -> AdminSession:
        if not settings.admin_email or not settings.admin_password_hash:
            raise api_error(
                "API_009",
                "Admin access is not configured.",
                503,
                "Set ADMIN_EMAIL and ADMIN_PASSWORD_HASH environment variables.",
            )
        normalized = self._normalize_email(email)
        if normalized != self._normalize_email(settings.admin_email):
            raise api_error("AUTH_001", "Invalid email or password.", 401)
        if not verify_password(password, settings.admin_password_hash):
            raise api_error("AUTH_001", "Invalid email or password.", 401)
        token = create_admin_token(ADMIN_USER_ID, normalized)
        self._log_admin_action(
            ADMIN_USER_ID,
            normalized,
            "admin_login",
            "auth",
            ADMIN_USER_ID,
            details={"ipAddress": ip_address},
            ip_address=ip_address,
        )
        return AdminSession(token=token, email=normalized)

    def admin_list_users(
        self,
        status: str | None = None,
        reported: bool | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        items: list[AdminUserSummary] = []
        for user in self.users.values():
            user_status = self._get_user_status(user.id)
            report_count = self._report_count_for_user(user.id)
            if status and user_status != status:
                continue
            if reported is True and report_count == 0:
                continue
            if reported is False and report_count > 0:
                continue
            if search:
                needle = search.strip().lower()
                if needle and needle not in user.displayName.lower() and needle not in user.id.lower():
                    email = self._lookup_user_email(user.id)
                    if not email or needle not in email.lower():
                        continue
            items.append(
                AdminUserSummary(
                    id=user.id,
                    displayName=user.displayName,
                    email=self._lookup_user_email(user.id),
                    age=user.age,
                    status=user_status,
                    reportCount=report_count,
                    lastActiveAt=user.lastActiveAt,
                    isOnline=user.isOnline,
                    verified=user.verified,
                    suspendedUntil=self.user_suspended_until.get(user.id),
                    bannedAt=self.user_banned_at.get(user.id),
                )
            )
        items.sort(key=lambda u: (-u.reportCount, u.displayName.lower()))
        total = len(items)
        return {"items": items[offset : offset + limit], "total": total, "limit": limit, "offset": offset}

    def admin_suspend_user(
        self,
        admin_id: str,
        admin_email: str,
        user_id: str,
        reason: str,
        duration_hours: int | None = None,
        ip_address: str | None = None,
    ) -> AdminUserSummary:
        user = self.users.get(user_id)
        if not user:
            raise api_error("API_003", "The requested resource was not found.", 404, "User not found.")
        if user_id == CURRENT_USER_ID:
            raise api_error("APP_002", "Please check your input and try again.", 400, "Cannot suspend the demo current user.")
        now = datetime.now(timezone.utc)
        self.user_status[user_id] = "suspended"
        self.user_moderation_reasons[user_id] = reason.strip()
        if duration_hours:
            self.user_suspended_until[user_id] = (now + timedelta(hours=duration_hours)).isoformat()
        else:
            self.user_suspended_until.pop(user_id, None)
        user.isOnline = False
        self._log_admin_action(
            admin_id,
            admin_email,
            "suspend_user",
            "user",
            user_id,
            details={"reason": reason, "durationHours": duration_hours},
            ip_address=ip_address,
        )
        return AdminUserSummary(
            id=user.id,
            displayName=user.displayName,
            email=self._lookup_user_email(user.id),
            age=user.age,
            status="suspended",
            reportCount=self._report_count_for_user(user.id),
            lastActiveAt=user.lastActiveAt,
            isOnline=user.isOnline,
            verified=user.verified,
            suspendedUntil=self.user_suspended_until.get(user.id),
            bannedAt=self.user_banned_at.get(user.id),
        )

    def admin_ban_user(
        self,
        admin_id: str,
        admin_email: str,
        user_id: str,
        reason: str,
        ip_address: str | None = None,
    ) -> AdminUserSummary:
        user = self.users.get(user_id)
        if not user:
            raise api_error("API_003", "The requested resource was not found.", 404, "User not found.")
        if user_id == CURRENT_USER_ID:
            raise api_error("APP_002", "Please check your input and try again.", 400, "Cannot ban the demo current user.")
        now = datetime.now(timezone.utc).isoformat()
        self.user_status[user_id] = "banned"
        self.user_banned_at[user_id] = now
        self.user_suspended_until.pop(user_id, None)
        self.user_moderation_reasons[user_id] = reason.strip()
        user.isOnline = False
        user.privacy.incognito = True
        for report in self.reports:
            if report.reportedUserId == user_id and report.status in ("submitted", "reviewing"):
                report.status = "action_taken"
                report.resolvedAt = now
                report.resolvedBy = admin_email
                report.resolution = "User banned"
        self._log_admin_action(
            admin_id,
            admin_email,
            "ban_user",
            "user",
            user_id,
            details={"reason": reason},
            ip_address=ip_address,
        )
        return AdminUserSummary(
            id=user.id,
            displayName=user.displayName,
            email=self._lookup_user_email(user.id),
            age=user.age,
            status="banned",
            reportCount=self._report_count_for_user(user.id),
            lastActiveAt=user.lastActiveAt,
            isOnline=user.isOnline,
            verified=user.verified,
            suspendedUntil=self.user_suspended_until.get(user.id),
            bannedAt=self.user_banned_at.get(user.id),
        )

    def admin_unsuspend_user(
        self,
        admin_id: str,
        admin_email: str,
        user_id: str,
        reason: str,
        ip_address: str | None = None,
    ) -> AdminUserSummary:
        user = self.users.get(user_id)
        if not user:
            raise api_error("API_003", "The requested resource was not found.", 404, "User not found.")
        if self._get_user_status(user_id) != "suspended":
            raise api_error("APP_002", "Please check your input and try again.", 400, "User is not suspended.")
        self.user_status.pop(user_id, None)
        self.user_suspended_until.pop(user_id, None)
        self.user_moderation_reasons.pop(user_id, None)
        self._log_admin_action(
            admin_id,
            admin_email,
            "unsuspend_user",
            "user",
            user_id,
            details={"reason": reason},
            ip_address=ip_address,
        )
        return AdminUserSummary(
            id=user.id,
            displayName=user.displayName,
            email=self._lookup_user_email(user.id),
            age=user.age,
            status="active",
            reportCount=self._report_count_for_user(user.id),
            lastActiveAt=user.lastActiveAt,
            isOnline=user.isOnline,
            verified=user.verified,
            suspendedUntil=self.user_suspended_until.get(user.id),
            bannedAt=self.user_banned_at.get(user.id),
        )

    def admin_list_reports(
        self,
        status: str | None = None,
        reason: str | None = None,
        reported_user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        items = list(self.reports)
        if status:
            items = [r for r in items if r.status == status]
        if reason:
            items = [r for r in items if r.reason == reason]
        if reported_user_id:
            items = [r for r in items if r.reportedUserId == reported_user_id]
        items.sort(key=lambda r: r.createdAt, reverse=True)
        total = len(items)
        return {
            "items": [r.model_copy() for r in items[offset : offset + limit]],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def admin_resolve_report(
        self,
        admin_id: str,
        admin_email: str,
        report_id: str,
        status: str,
        resolution: str,
        resolution_note: str | None = None,
        ip_address: str | None = None,
    ) -> UserReport:
        report = next((r for r in self.reports if r.id == report_id), None)
        if not report:
            raise api_error("API_003", "The requested resource was not found.", 404, "Report not found.")
        if report.status in ("action_taken", "dismissed"):
            raise api_error("API_007", "This action conflicts with existing data.", 409, "Report is already resolved.")
        now = datetime.now(timezone.utc).isoformat()
        report.status = status
        report.resolution = resolution.strip()
        report.resolutionNote = resolution_note
        report.resolvedAt = now
        report.resolvedBy = admin_email
        self._log_admin_action(
            admin_id,
            admin_email,
            "resolve_report",
            "report",
            report_id,
            details={"status": status, "resolution": resolution, "reportedUserId": report.reportedUserId},
            ip_address=ip_address,
        )
        return report.model_copy()

    def admin_list_content(
        self,
        status: str | None = None,
        content_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        items = list(self.content_items)
        if status:
            items = [item for item in items if item.status == status]
        if content_type:
            items = [item for item in items if item.contentType == content_type]
        items.sort(key=lambda item: item.createdAt, reverse=True)
        total = len(items)
        return {
            "items": [item.model_copy() for item in items[offset : offset + limit]],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def admin_moderate_content(
        self,
        admin_id: str,
        admin_email: str,
        content_id: str,
        action: str,
        note: str | None = None,
        ip_address: str | None = None,
    ) -> ContentModerationItem:
        item = next((c for c in self.content_items if c.id == content_id), None)
        if not item:
            raise api_error("API_003", "The requested resource was not found.", 404, "Content item not found.")
        if item.status != "pending":
            raise api_error("API_007", "This action conflicts with existing data.", 409, "Content already reviewed.")
        now = datetime.now(timezone.utc).isoformat()
        audit_action = {"approve": "approve_content", "reject": "reject_content", "remove": "remove_content"}[action]
        status_map = {"approve": "approved", "reject": "rejected", "remove": "removed"}
        item.status = status_map[action]
        item.reviewedAt = now
        item.reviewedBy = admin_email
        user = self.users.get(item.userId)
        if user and action == "remove":
            if item.contentType == "profile":
                user.photos = []
                user.bio = "[Profile removed by moderation]"
            elif item.contentType == "photo" and item.photoUrl and item.photoUrl in user.photos:
                user.photos = [p for p in user.photos if p != item.photoUrl]
        self._log_admin_action(
            admin_id,
            admin_email,
            audit_action,
            "content",
            content_id,
            details={"action": action, "note": note, "userId": item.userId},
            ip_address=ip_address,
        )
        return item.model_copy()

    def admin_get_audit_log(
        self,
        action: str | None = None,
        admin_id: str | None = None,
        target_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        items = list(self.audit_logs)
        if action:
            items = [entry for entry in items if entry.action == action]
        if admin_id:
            items = [entry for entry in items if entry.adminId == admin_id]
        if target_id:
            items = [entry for entry in items if entry.targetId == target_id]
        total = len(items)
        return {
            "items": [entry.model_copy() for entry in items[offset : offset + limit]],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

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

    def scan_media(
        self,
        file_name: str,
        content_type: str | None = None,
        file_size: int | None = None,
        kind: str | None = None,
    ) -> dict:
        """Structured pre-upload validation. Hook a real classifier at the marked integration point."""
        if not file_name or not file_name.strip():
            return {"ok": False, "reason": "File name is required."}
        if len(file_name) > MAX_FILENAME_LENGTH:
            return {"ok": False, "reason": f"File name must be {MAX_FILENAME_LENGTH} characters or fewer."}

        lowered = file_name.lower()
        ext = "." + lowered.rsplit(".", 1)[-1] if "." in lowered else ""
        media_kind = kind or ("video" if ext in ALLOWED_VIDEO_EXTENSIONS else "image")

        allowed_ext = ALLOWED_VIDEO_EXTENSIONS if media_kind == "video" else ALLOWED_IMAGE_EXTENSIONS
        if ext not in allowed_ext:
            return {"ok": False, "reason": "File type is not allowed."}

        if content_type:
            allowed_mimes = ALLOWED_VIDEO_MIMES if media_kind == "video" else ALLOWED_IMAGE_MIMES
            if content_type.lower() not in allowed_mimes:
                return {"ok": False, "reason": "Content type is not allowed."}

        if file_size is not None:
            max_bytes = MAX_VIDEO_BYTES if media_kind == "video" else MAX_IMAGE_BYTES
            if file_size <= 0 or file_size > max_bytes:
                return {"ok": False, "reason": "File exceeds the maximum allowed size."}

        # Integration point: replace with PhotoDNA / Rekognition / vendor classifier.
        if "illegal" in lowered or "csam" in lowered:
            return {"ok": False, "reason": "This file was blocked by the safety filter."}
        return {"ok": True}

    def create_presigned_upload(self, request: PresignUploadRequest, user_id: str) -> PresignResponse:
        if not request.fileName or not request.fileName.strip():
            raise api_error("APP_002", "Please check your input and try again.", 400, "File name is required.")
        if len(request.fileName) > MAX_FILENAME_LENGTH:
            raise api_error(
                "APP_002",
                "Please check your input and try again.",
                400,
                f"File name must be {MAX_FILENAME_LENGTH} characters or fewer.",
            )
        max_bytes = MAX_VIDEO_BYTES if request.kind == "video" else MAX_IMAGE_BYTES
        if request.fileSizeBytes is not None and (
            request.fileSizeBytes <= 0 or request.fileSizeBytes > max_bytes
        ):
            raise api_error("APP_002", "Please check your input and try again.", 400, "File exceeds the maximum allowed size.")

        scan = self.scan_media(
            request.fileName,
            content_type=request.contentType,
            file_size=request.fileSizeBytes,
            kind=request.kind,
        )
        if not scan.get("ok"):
            raise api_error("APP_002", "Please check your input and try again.", 400, scan.get("reason"))

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

    def update_push_token(self, token: str) -> User:
        me = self._get_me()
        me.pushToken = token.strip() or None
        return self._apply_distance(me)

    def conversation_participant_ids(self, conversation_id: str) -> list[str]:
        conv = next((c for c in self.conversations if c.id == conversation_id), None)
        return conv.participantIds if conv else []

    def find_message_by_client_id(self, client_id: str) -> Message | None:
        return next((m for m in self.messages if m.clientId == client_id), None)


store = DataStore()
