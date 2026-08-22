from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


class UserPrivacy(BaseModel):
    showOnMap: bool = True
    hideDistance: bool = False
    incognito: bool = False
    profileVisibility: Literal["everyone", "nearby", "hidden"] = "everyone"
    shareApproximateLocation: bool = True
    showOnlineStatus: bool = True


class AlbumMedia(BaseModel):
    id: str
    kind: Literal["image", "video"]
    url: str
    thumbnailUrl: str | None = None


class PhotoAlbum(BaseModel):
    id: str
    title: str
    items: list[AlbumMedia] = Field(default_factory=list)
    nsfw: bool = False
    locked: bool = False


class User(BaseModel):
    id: str
    displayName: str
    age: int
    birthDate: str | None = None
    bio: str | None = None
    photos: list[str] = Field(default_factory=list)
    geohash: str
    latitude: float
    longitude: float
    lastActiveAt: str
    isOnline: bool = False
    distanceMeters: float | None = None
    stats: dict[str, str] | None = None
    tags: list[str] | None = None
    kinks: list[str] | None = None
    albums: list[PhotoAlbum] | None = None
    privacy: UserPrivacy
    hostingTag: str | None = None
    verified: bool | None = None
    premium: bool | None = None
    boostedUntil: str | None = None
    pushToken: str | None = None


class UpdateProfileInput(BaseModel):
    displayName: str | None = None
    age: int | None = None
    bio: str | None = None
    photos: list[str] | None = None
    tags: list[str] | None = None
    kinks: list[str] | None = None
    albums: list[PhotoAlbum] | None = None
    stats: dict[str, str] | None = None
    hostingTag: str | None = None
    verified: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    geohash: str | None = None


class PushTokenInput(BaseModel):
    token: str


class WsTicketResponse(BaseModel):
    ticket: str


class Message(BaseModel):
    id: str
    conversationId: str
    senderId: str
    body: str
    createdAt: str
    status: Literal["pending", "sent", "delivered", "read", "failed"] | None = None
    clientId: str | None = None
    mediaUrl: str | None = None
    mediaType: Literal["image", "video"] | None = None
    thumbnailUrl: str | None = None
    viewOnce: bool | None = None
    viewedAt: str | None = None
    editedAt: str | None = None
    deletedAt: str | None = None


class Conversation(BaseModel):
    id: str
    participantIds: list[str]
    lastMessage: Message | None = None
    unreadCount: int = 0
    title: str | None = None
    isGroup: bool | None = None


class Event(BaseModel):
    id: str
    title: str
    description: str
    startsAt: str
    venueName: str
    latitude: float
    longitude: float
    hostId: str
    attendeeIds: list[str] = Field(default_factory=list)
    coverImageUrl: str | None = None
    distanceMeters: float | None = None


class AuthSession(BaseModel):
    token: str
    user: User
    onboarded: bool = False


class RegisterInput(BaseModel):
    email: str
    password: str
    displayName: str
    age: int
    birthDate: str | None = None


class ConsentRecord(BaseModel):
    type: str
    version: str
    acceptedAt: str


class ConsentInput(BaseModel):
    type: str
    version: str = "1.0"


DataExportStatus = Literal["pending", "processing", "completed", "failed"]


class DataExportRequest(BaseModel):
    id: str
    userId: str
    status: DataExportStatus
    requestedAt: str
    completedAt: str | None = None


class LoginInput(BaseModel):
    email: str
    password: str


class PasswordResetRequestResult(BaseModel):
    sent: bool
    demoCode: str | None = None


class UserSettings(BaseModel):
    email: str
    showOnMap: bool = True
    hideDistance: bool = False
    incognito: bool = False
    profileVisibility: Literal["everyone", "nearby", "hidden"] = "everyone"
    shareApproximateLocation: bool = True
    showOnlineStatus: bool = True
    notifyMessages: bool = True
    notifyTaps: bool = True
    notifyEvents: bool = True
    defaultRadiusMeters: int = 5000
    distanceUnit: Literal["km", "mi"] = "km"
    ageMin: int = 18
    ageMax: int = 99
    emailVerified: bool = False
    requireMutualMatch: bool = False
    travelCityId: str | None = None
    premium: bool = False


class ProfileActivityItem(BaseModel):
    user: User
    at: str


class ProfileActivitySummary(BaseModel):
    viewsCount: int
    likesCount: int
    tapsCount: int


class TouchEvent(BaseModel):
    id: str
    type: str
    actorUserId: str
    targetUserId: str | None = None
    screen: str | None = None
    createdAt: str
    metadata: dict[str, Any] | None = None


class TrackTouchEventInput(BaseModel):
    type: str
    actorUserId: str
    targetUserId: str | None = None
    screen: str | None = None
    metadata: dict[str, Any] | None = None


ReportStatus = Literal["submitted", "reviewing", "action_taken", "dismissed"]
UserModerationStatus = Literal["active", "suspended", "banned"]
ReportReason = Literal["spam", "harassment", "inappropriate", "fake", "underage", "other"]
ContentType = Literal["profile", "photo"]
ContentModerationStatus = Literal["pending", "approved", "rejected", "removed"]
AuditAction = Literal[
    "admin_login",
    "suspend_user",
    "ban_user",
    "unsuspend_user",
    "resolve_report",
    "approve_content",
    "reject_content",
    "remove_content",
]


class UserReport(BaseModel):
    id: str
    reportedUserId: str
    reporterUserId: str | None = None
    conversationId: str | None = None
    reason: ReportReason
    details: str | None = None
    createdAt: str
    status: ReportStatus
    resolvedAt: str | None = None
    resolvedBy: str | None = None
    resolution: str | None = None
    resolutionNote: str | None = None


class AppNotification(BaseModel):
    id: str
    type: str
    title: str
    body: str
    createdAt: str
    read: bool
    userId: str | None = None
    conversationId: str | None = None
    eventId: str | None = None


class CreateNotificationInput(BaseModel):
    type: str
    title: str
    body: str
    userId: str | None = None
    conversationId: str | None = None
    eventId: str | None = None


class CreateEventInput(BaseModel):
    title: str
    description: str
    venueName: str
    startsAt: str
    coverImageUrl: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class UpdateEventInput(BaseModel):
    title: str | None = None
    description: str | None = None
    venueName: str | None = None
    startsAt: str | None = None
    coverImageUrl: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class PresignUploadRequest(BaseModel):
    fileName: str
    contentType: str
    kind: Literal["image", "video"]
    folder: str | None = None
    fileSizeBytes: int | None = None


class PresignResponse(BaseModel):
    key: str
    uploadUrl: str
    publicUrl: str
    headers: dict[str, str] = Field(default_factory=dict)
    expiresInSeconds: int = 900
    mode: Literal["s3", "mock"] = "mock"


class MediaScanResult(BaseModel):
    ok: bool
    reason: str | None = None


class SocialLoginInput(BaseModel):
    provider: Literal["apple", "google", "facebook"]
    idToken: str | None = None
    accessToken: str | None = None
    email: str | None = None
    displayName: str | None = None


class TokenPayload(BaseModel):
    sub: str
    email: str
    exp: datetime
    role: Literal["user", "admin"] = "user"


class AdminLoginInput(BaseModel):
    email: str
    password: str


class AdminSession(BaseModel):
    token: str
    email: str
    role: Literal["admin"] = "admin"


class AdminUserSummary(BaseModel):
    id: str
    displayName: str
    email: str | None = None
    age: int
    status: UserModerationStatus
    reportCount: int
    lastActiveAt: str
    isOnline: bool
    verified: bool | None = None
    suspendedUntil: str | None = None
    bannedAt: str | None = None


class SuspendUserInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    durationHours: int | None = Field(default=None, ge=1, le=8760)


class BanUserInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class UnsuspendUserInput(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ResolveReportInput(BaseModel):
    status: Literal["action_taken", "dismissed"]
    resolution: str = Field(min_length=1, max_length=500)
    resolutionNote: str | None = Field(default=None, max_length=2000)


class ContentModerationItem(BaseModel):
    id: str
    contentType: ContentType
    userId: str
    userDisplayName: str
    photoUrl: str | None = None
    status: ContentModerationStatus
    reportId: str | None = None
    reason: str | None = None
    createdAt: str
    reviewedAt: str | None = None
    reviewedBy: str | None = None


class ModerateContentInput(BaseModel):
    action: Literal["approve", "reject", "remove"]
    note: str | None = Field(default=None, max_length=2000)


class AdminAuditLogEntry(BaseModel):
    id: str
    adminId: str
    adminEmail: str
    action: AuditAction
    targetType: Literal["user", "report", "content", "auth"]
    targetId: str
    details: dict[str, Any] | None = None
    createdAt: str
    ipAddress: str | None = None
