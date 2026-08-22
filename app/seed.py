from datetime import datetime, timedelta, timezone

from app.geo import MOCK_LOCATION, random_offset
from app.geohash import encode_geohash
from app.models import (
    AppNotification,
    Conversation,
    Event,
    Message,
    PhotoAlbum,
    User,
    UserPrivacy,
    UserSettings,
)

CURRENT_USER_ID = "user-me"
SAMPLE_VIDEO_URL = (
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4"
)

NAMES = [
    "Alex", "Jordan", "Casey", "Riley", "Morgan", "Quinn", "Avery", "Blake",
    "Cameron", "Drew", "Elliot", "Finley", "Gray", "Harper", "Indigo", "Jamie",
    "Kai", "Logan", "Marley", "Noah", "Oakley", "Parker", "Reese", "Sage",
    "Taylor", "Val", "Winter", "Zion", "Adrian", "Bennett", "Cole", "Dylan",
    "Emery", "Frankie", "Glen", "Hayden", "Ivan", "Jesse", "Keegan", "Lane",
]

BODY_TYPES = ["Slim", "Average", "Athletic", "Muscular", "Stocky"]
HIV_RESULTS = ["Negative", "Negative on PrEP", "Undetectable", "Unknown"]
TAGS = ["Friends", "Dates", "Networking", "Right now", "Chat", "Events"]
KINKS = ["Vanilla", "Kink-friendly", "Dom", "Sub", "Switch", "Open-minded"]


def photo_seed(seed: str) -> str:
    return f"https://picsum.photos/seed/{seed}/400/600"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_seed_users() -> list[User]:
    users: list[User] = []
    for i, name in enumerate(NAMES):
        user_id = CURRENT_USER_ID if i == 0 else f"user-{i}"
        coords = MOCK_LOCATION if i == 0 else random_offset(8000, MOCK_LOCATION)
        age = 21 + (i % 15)
        albums: list[PhotoAlbum] | None = None
        if i == 0 or i % 3 == 0:
            albums = [
                PhotoAlbum(
                    id=f"album-{user_id}-nsfw",
                    title="NSFW",
                    nsfw=True,
                    items=[
                        {"id": f"{user_id}-nsfw-1", "kind": "image", "url": photo_seed(f"{user_id}-nsfw-1")},
                        {
                            "id": f"{user_id}-nsfw-2",
                            "kind": "video",
                            "url": SAMPLE_VIDEO_URL,
                            "thumbnailUrl": photo_seed(f"{user_id}-nsfw-2"),
                        },
                        {"id": f"{user_id}-nsfw-3", "kind": "image", "url": photo_seed(f"{user_id}-nsfw-3")},
                    ],
                )
            ]
        users.append(
            User(
                id=user_id,
                displayName="You" if i == 0 else name,
                age=age,
                bio="Looking to meet new people nearby."
                if i == 0
                else f"Hey, I'm {name}. Let's connect!",
                photos=[photo_seed(user_id if j == 0 else f"{user_id}-{j + 1}") for j in range(1 + (i % 4))],
                geohash=encode_geohash(coords["latitude"], coords["longitude"]),
                latitude=coords["latitude"],
                longitude=coords["longitude"],
                lastActiveAt=(_now() - timedelta(hours=i)).isoformat(),
                isOnline=i < 8 or i == 0,
                stats={
                    "Height": f"{170 + (i % 20)}cm",
                    "Weight": f"{65 + (i % 25)}kg",
                    "Body type": BODY_TYPES[i % len(BODY_TYPES)],
                    **({} if i != 0 and i % 4 == 0 else {"HIV results": HIV_RESULTS[i % len(HIV_RESULTS)]}),
                },
                tags=[TAGS[i % len(TAGS)], TAGS[(i + 3) % len(TAGS)]],
                kinks=[KINKS[i % len(KINKS)], KINKS[(i + 5) % len(KINKS)]],
                albums=albums,
                privacy=UserPrivacy(
                    showOnMap=True,
                    hideDistance=False,
                    incognito=i % 17 == 0,
                    profileVisibility="hidden" if i % 17 == 0 else "everyone",
                    shareApproximateLocation=i % 23 != 0,
                    showOnlineStatus=i % 11 != 0,
                ),
                hostingTag="Hosting" if i % 5 == 0 else ("Visiting" if i % 5 == 2 else None),
                verified=i % 4 == 0,
                premium=i % 7 == 0,
            )
        )
    return users


def build_seed_conversations() -> list[Conversation]:
    return [
        Conversation(
            id="conv-group-1",
            participantIds=[CURRENT_USER_ID, "user-2", "user-3", "user-5"],
            unreadCount=1,
            isGroup=True,
            title="Saturday plans",
        ),
        Conversation(id="conv-1", participantIds=[CURRENT_USER_ID, "user-2"], unreadCount=2),
        Conversation(id="conv-2", participantIds=[CURRENT_USER_ID, "user-3"], unreadCount=0),
        Conversation(id="conv-3", participantIds=[CURRENT_USER_ID, "user-5"], unreadCount=1),
        Conversation(id="conv-4", participantIds=[CURRENT_USER_ID, "user-7"], unreadCount=0),
        Conversation(id="conv-5", participantIds=[CURRENT_USER_ID, "user-9"], unreadCount=3),
        Conversation(id="conv-6", participantIds=[CURRENT_USER_ID, "user-11"], unreadCount=0),
        Conversation(id="conv-7", participantIds=[CURRENT_USER_ID, "user-13"], unreadCount=0),
        Conversation(id="conv-8", participantIds=[CURRENT_USER_ID, "user-15"], unreadCount=1),
    ]


def build_seed_messages(now: datetime) -> list[Message]:
    messages: list[Message] = []
    for i in range(24):
        messages.append(
            Message(
                id=f"msg-old-{i + 1}",
                conversationId="conv-1",
                senderId="user-2" if i % 2 == 0 else CURRENT_USER_ID,
                body=f"Earlier from Casey #{i + 1}" if i % 2 == 0 else f"Earlier reply #{i + 1}",
                createdAt=(now - timedelta(days=2) - timedelta(minutes=(24 - i) * 10)).isoformat(),
                status="read",
            )
        )
    messages.extend(
        [
            Message(
                id="msg-group-1",
                conversationId="conv-group-1",
                senderId="user-3",
                body="Who is still in for Saturday?",
                createdAt=(now - timedelta(minutes=90)).isoformat(),
                status="delivered",
            ),
            Message(
                id="msg-group-2",
                conversationId="conv-group-1",
                senderId=CURRENT_USER_ID,
                body="I am. Rooftop still good?",
                createdAt=(now - timedelta(minutes=86)).isoformat(),
                status="read",
            ),
            Message(
                id="msg-1",
                conversationId="conv-1",
                senderId="user-2",
                body="Hey! How are you?",
                createdAt=(now - timedelta(hours=2)).isoformat(),
                status="read",
            ),
            Message(
                id="msg-2",
                conversationId="conv-1",
                senderId=CURRENT_USER_ID,
                body="Good! You nearby tonight?",
                createdAt=(now - timedelta(hours=1, minutes=55)).isoformat(),
                status="read",
            ),
            Message(
                id="msg-3",
                conversationId="conv-1",
                senderId="user-2",
                body="Yeah, free after 9",
                createdAt=(now - timedelta(hours=1, minutes=50)).isoformat(),
                status="delivered",
            ),
            Message(
                id="msg-4",
                conversationId="conv-1",
                senderId="user-2",
                body="Want to grab a drink?",
                createdAt=(now - timedelta(hours=1, minutes=45)).isoformat(),
                status="delivered",
            ),
            Message(
                id="msg-5",
                conversationId="conv-2",
                senderId="user-3",
                body="Nice profile pic!",
                createdAt=(now - timedelta(days=1)).isoformat(),
                status="read",
            ),
            Message(
                id="msg-6",
                conversationId="conv-2",
                senderId=CURRENT_USER_ID,
                body="Thanks! Same to you",
                createdAt=(now - timedelta(hours=23)).isoformat(),
                status="read",
            ),
            Message(
                id="msg-7",
                conversationId="conv-3",
                senderId="user-5",
                body="Hosting tonight if you are interested",
                createdAt=(now - timedelta(hours=1)).isoformat(),
                status="delivered",
            ),
            Message(
                id="msg-16",
                conversationId="conv-1",
                senderId="user-2",
                body="",
                createdAt=(now - timedelta(hours=1, minutes=40)).isoformat(),
                status="delivered",
                mediaUrl=photo_seed("chat-conv1-photo"),
                mediaType="image",
            ),
            Message(
                id="msg-17",
                conversationId="conv-1",
                senderId=CURRENT_USER_ID,
                body="",
                createdAt=(now - timedelta(minutes=2)).isoformat(),
                status="sent",
                mediaUrl=photo_seed("chat-conv1-me-vo"),
                mediaType="image",
                viewOnce=True,
                viewedAt=None,
            ),
        ]
    )
    return messages


def build_seed_events(now: datetime) -> list[Event]:
    return [
        Event(
            id="event-1",
            title="Rooftop Mixer",
            description="Casual rooftop hangout with drinks and music. All welcome!",
            startsAt=(now + timedelta(days=1)).isoformat(),
            venueName="Sky Lounge NYC",
            latitude=MOCK_LOCATION["latitude"] + 0.005,
            longitude=MOCK_LOCATION["longitude"] - 0.003,
            hostId="user-4",
            attendeeIds=["user-2", "user-6", "user-8", CURRENT_USER_ID],
            coverImageUrl=photo_seed("event-1"),
        ),
        Event(
            id="event-2",
            title="Pride Week Kickoff",
            description="Celebrate the start of pride week with the community.",
            startsAt=(now + timedelta(days=2)).isoformat(),
            venueName="West Village Park",
            latitude=MOCK_LOCATION["latitude"] - 0.008,
            longitude=MOCK_LOCATION["longitude"] + 0.006,
            hostId="user-10",
            attendeeIds=["user-1", "user-3", "user-12"],
            coverImageUrl=photo_seed("event-2"),
        ),
        Event(
            id="event-3",
            title="Sunday Brunch Social",
            description="Low-key brunch meetup. RSVP for the table reservation.",
            startsAt=(now + timedelta(days=3)).isoformat(),
            venueName="Corner Cafe",
            latitude=MOCK_LOCATION["latitude"] + 0.002,
            longitude=MOCK_LOCATION["longitude"] + 0.004,
            hostId="user-6",
            attendeeIds=["user-5", "user-14"],
            coverImageUrl=photo_seed("event-3"),
        ),
        Event(
            id="event-4",
            title="DJ Night",
            description="Dance floor open until late. Dress code: come as you are.",
            startsAt=(now + timedelta(hours=12)).isoformat(),
            venueName="Pulse Club",
            latitude=MOCK_LOCATION["latitude"] - 0.004,
            longitude=MOCK_LOCATION["longitude"] - 0.005,
            hostId="user-8",
            attendeeIds=["user-7", "user-9", "user-11", "user-16"],
            coverImageUrl=photo_seed("event-4"),
        ),
    ]


def build_seed_notifications(now: datetime) -> list[AppNotification]:
    return [
        AppNotification(
            id="notif-1",
            type="like",
            title="Casey liked you",
            body="Casey liked your profile",
            createdAt=(now - timedelta(minutes=20)).isoformat(),
            read=False,
            userId="user-2",
        ),
        AppNotification(
            id="notif-2",
            type="tap",
            title="Riley tapped you",
            body="Riley tapped your profile",
            createdAt=(now - timedelta(minutes=10)).isoformat(),
            read=False,
            userId="user-3",
        ),
        AppNotification(
            id="notif-3",
            type="message",
            title="New message from Casey",
            body="Want to grab a drink?",
            createdAt=(now - timedelta(hours=1, minutes=45)).isoformat(),
            read=False,
            userId="user-2",
            conversationId="conv-1",
        ),
        AppNotification(
            id="notif-4",
            type="event",
            title="DJ Night is tonight",
            body="Pulse Club · happening nearby",
            createdAt=(now - timedelta(hours=1, minutes=30)).isoformat(),
            read=True,
            eventId="event-4",
        ),
    ]


def default_settings() -> UserSettings:
    return UserSettings(email="you@example.com")
