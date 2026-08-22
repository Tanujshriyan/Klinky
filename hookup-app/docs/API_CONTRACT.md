# FastAPI + Postgres API Contract (Phase 2)

This document describes the backend contract for the Pulse hookup messaging app. Phase 1 uses mock services; swap `MockApiService` and `MockWebSocketClient` for the HTTP/WS clients described here.

## Authentication

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/auth/register` | `{ email, password, displayName, age }` | `{ token, user, onboarded? }` |
| POST | `/auth/login` | `{ email, password }` | `{ token, user, onboarded? }` |
| POST | `/auth/change-password` | `{ currentPassword, newPassword }` | `204` |
| DELETE | `/auth/account` | — | `204` |
| POST | `/auth/forgot-password` | `{ email }` | `{ sent: true }` |
| POST | `/auth/reset-password` | `{ email, code, newPassword }` | `204` |
| POST | `/auth/change-email` | `{ email }` | `{ sent: true, demoCode? }` |
| POST | `/auth/verify-email` | `{ code }` | `204` |
| POST | `/auth/social` | `{ provider: apple\|google\|facebook, idToken?, accessToken?, email?, displayName? }` | `{ token, user, onboarded? }` |
| POST | `/auth/ws-ticket` | — (Bearer required) | `{ ticket }` |

JWT is passed as `Authorization: Bearer <token>` on REST calls.

For WebSocket, use a **short-lived ticket** (preferred):

1. `POST /auth/ws-ticket` with `Authorization: Bearer <jwt>` → `{ "ticket": "..." }`
2. Connect: `WS /ws/chat?ticket=<ticket>` (60s TTL)

Legacy `?token=<jwt>` is still accepted but discouraged.

---

## Users

| Method | Path | Description |
|--------|------|-------------|
| GET | `/users/me` | Current user profile |
| PATCH | `/users/me` | Update profile fields |
| PATCH | `/users/me/push-token` | `{ token }` — Expo push token |
| POST | `/users/me/consents` | `{ type, version }` — consent audit trail |
| POST | `/users/me/data-export` | Queue data export → `{ requestId, status }` |
| GET | `/users/me/data-export/{id}` | Export request status |
| GET | `/users/nearby?lat=&lng=&radius=&online_only=&age_min=&age_max=&sort=` | Geo discovery (PostGIS) |
| GET | `/users/{id}` | Public profile |
| POST | `/users/me/verify` | Request verification badge |
| POST | `/users/me/boost` | Pin profile to Nearby for 30 minutes |
| POST | `/users/{id}/like` | Like profile |
| DELETE | `/users/{id}/like` | Remove like |
| POST | `/users/{id}/tap` | Tap profile |
| GET | `/users/me/favorites` | Saved profiles |
| POST | `/users/{id}/favorite` | Save profile |
| DELETE | `/users/{id}/favorite` | Unsave profile |
| POST | `/moderation/scan` | `{ fileName }` → `{ ok, reason? }` |

---

## Conversations (REST bootstrap)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/conversations` | Inbox list with last message + unread count |
| POST | `/conversations` | `{ participantId }` → create or return existing |
| GET | `/conversations/{id}/messages?cursor=&limit=20` | Paginated history (newest first) |
| POST | `/conversations/group` | `{ participantIds, title }` |
| POST | `/conversations/{id}/read` | Mark conversation read |
| PATCH | `/messages/{id}` | `{ body }` edit own message |
| DELETE | `/messages/{id}` | Soft-delete own message |

**Note:** Message send/receive is WebSocket-only. REST does not accept new messages.

---

## WebSocket — `WS /ws/chat?ticket=<ticket>`

Preferred: obtain ticket via `POST /auth/ws-ticket`, then connect with `?ticket=`. Legacy `?token=<jwt>` still supported.

### Client → Server events

```json
{ "type": "message.send", "conversationId": "...", "body": "...", "clientId": "..." }
{ "type": "typing.start", "conversationId": "..." }
{ "type": "typing.stop", "conversationId": "..." }
{ "type": "message.read", "conversationId": "...", "messageId": "..." }
{ "type": "subscribe", "conversationId": "..." }
{ "type": "unsubscribe", "conversationId": "..." }
{ "type": "ping" }
```

### Server → Client events

```json
{ "type": "message.new", "message": { "id", "conversationId", "senderId", "body", "createdAt", "status" } }
{ "type": "message.ack", "clientId": "...", "message": { ... } }
{ "type": "message.read", "conversationId": "...", "messageId": "...", "readBy": "..." }
{ "type": "typing.start", "conversationId": "...", "userId": "..." }
{ "type": "typing.stop", "conversationId": "...", "userId": "..." }
{ "type": "presence.update", "userId": "...", "isOnline": true }
{ "type": "pong" }
{ "type": "error", "code": "...", "message": "..." }
```

### Server behavior

1. Validate JWT on connect; reject with close code 4001 if invalid.
2. Auto-join user to all their conversation rooms.
3. On `message.send`: INSERT to Postgres (idempotent on `client_id`), then emit `message.ack` to sender and `message.new` to all room participants.
4. On connect/disconnect: broadcast `presence.update` to users who share a conversation.

---

## Events

| Method | Path | Description |
|--------|------|-------------|
| GET | `/events?filter=today\|week\|hosting` | List events |
| GET | `/events/{id}` | Event detail |
| POST | `/events` | Create event |
| POST | `/events/{id}/rsvp` | RSVP current user |
| DELETE | `/events/{id}/rsvp` | Cancel RSVP |
| PATCH | `/events/{id}` | Update hosted event |
| DELETE | `/events/{id}` | Delete hosted event |
| GET | `/events/{id}/attendees` | Attendee profiles |
| POST | `/events/notify-new` | Create alerts for unseen nearby events |

---

## Settings & Safety

| Method | Path | Description |
|--------|------|-------------|
| GET | `/settings` | User preferences |
| PATCH | `/settings` | Partial update |
| POST | `/blocks` | `{ userId }` |
| GET | `/blocks` | Blocked user list |
| POST | `/reports` | `{ userId, reason, details? }` |
| GET | `/reports` | Current user's report follow-up statuses |

---

## Postgres Schema (highlights)

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  age INT NOT NULL CHECK (age >= 18),
  bio TEXT,
  location GEOGRAPHY(POINT, 4326),
  last_active_at TIMESTAMPTZ DEFAULT now(),
  is_online BOOLEAN DEFAULT false,
  stats JSONB DEFAULT '{}',
  tags TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE photos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  sort_order INT DEFAULT 0
);

CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE conversation_participants (
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  PRIMARY KEY (conversation_id, user_id)
);

CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  sender_id UUID REFERENCES users(id),
  body TEXT NOT NULL,
  client_id TEXT UNIQUE,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at DESC);

CREATE TABLE message_reads (
  message_id UUID REFERENCES messages(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),
  read_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (message_id, user_id)
);

CREATE TABLE events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  description TEXT,
  starts_at TIMESTAMPTZ NOT NULL,
  venue_name TEXT,
  location GEOGRAPHY(POINT, 4326),
  host_id UUID REFERENCES users(id),
  cover_image_url TEXT
);

CREATE TABLE event_rsvps (
  event_id UUID REFERENCES events(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),
  PRIMARY KEY (event_id, user_id)
);

CREATE TABLE user_settings (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  show_on_map BOOLEAN DEFAULT true,
  hide_distance BOOLEAN DEFAULT false,
  incognito BOOLEAN DEFAULT false,
  notify_messages BOOLEAN DEFAULT true,
  notify_taps BOOLEAN DEFAULT true,
  notify_events BOOLEAN DEFAULT true,
  default_radius_meters INT DEFAULT 5000,
  age_min INT DEFAULT 21,
  age_max INT DEFAULT 45
);

CREATE TABLE blocks (
  blocker_id UUID REFERENCES users(id),
  blocked_id UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (blocker_id, blocked_id)
);
```

### Nearby users query (PostGIS)

```sql
SELECT u.*, ST_Distance(u.location, ST_MakePoint(:lng, :lat)::geography) AS distance_meters
FROM users u
WHERE u.id != :current_user_id
  AND NOT u.incognito
  AND ST_DWithin(u.location, ST_MakePoint(:lng, :lat)::geography, :radius_meters)
ORDER BY distance_meters;
```

---

## Client swap checklist

1. Set `EXPO_PUBLIC_API_HOST` to your FastAPI host.
2. Set `EXPO_PUBLIC_USE_MOCK_API=false` so screens use `HttpApiService` via `src/services/api/client.ts`.
3. Set `EXPO_PUBLIC_USE_MOCK_WS=false` so chat uses `ChatWebSocketClient`.
4. Optional: set `EXPO_PUBLIC_API_PROTOCOL=http` for a local FastAPI server (default for localhost).

---

## Error codes

All errors use the format `{ code, message, details?, retryable? }`. Codes are defined in [`src/services/errors/codes.ts`](../src/services/errors/codes.ts).

### Network (`NET_*`)

| Code | Description | Retryable |
|------|-------------|-----------|
| `NET_001` | Device offline | No |
| `NET_002` | Request timeout | Yes |
| `NET_003` | Connection failed | Yes |
| `NET_004` | DNS resolution failed | No |
| `NET_005` | CORS blocked (web) | No |

### WebSocket (`WS_*`)

| Code | Description | Retryable |
|------|-------------|-----------|
| `WS_001` | Connect failed | Yes |
| `WS_002` | Disconnected | Yes |
| `WS_003` | Auth failed (close 4001) | No |
| `WS_004` | Reconnect attempts exhausted | Yes |
| `WS_005` | Heartbeat timeout | Yes |
| `WS_006` | Malformed server event | No |

### REST API (`API_*`)

| Code | HTTP | Description |
|------|------|-------------|
| `API_001` | 5xx | Server error |
| `API_002` | 400 | Bad request |
| `API_003` | 404 | Not found |
| `API_004` | 429 | Rate limited |
| `API_005` | 401 | Unauthorized |
| `API_006` | 403 | Forbidden |
| `API_007` | 409 | Conflict |

### Auth (`AUTH_*`)

| Code | Description |
|------|-------------|
| `AUTH_001` | Invalid credentials |
| `AUTH_002` | Session expired |
| `AUTH_003` | Unauthorized |
| `AUTH_004` | Account blocked |

### Messaging (`MSG_*`)

| Code | Description |
|------|-------------|
| `MSG_001` | Send failed |
| `MSG_002` | Outbound queue full |
| `MSG_003` | Conversation not found |

### Resources (`RES_*`)

| Code | Description |
|------|-------------|
| `RES_001` | User not found |
| `RES_002` | Event not found |
| `RES_003` | Load failed |

### FastAPI error response example

```json
{
  "code": "API_005",
  "message": "Session expired. Please sign in again.",
  "details": "JWT expired",
  "retryable": false
}
```

### WebSocket error event

```json
{ "type": "error", "code": "WS_003", "message": "Chat session expired.", "retryable": false }
```
