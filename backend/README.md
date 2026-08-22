# Pulse API (FastAPI)

Backend for the Pulse mobile app: auth, discovery, real-time chat (WebSocket), privacy controls, compliance APIs, admin moderation, and push dispatch.

## Quick start

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
python main.py
```

API: `http://localhost:8000`  
Health: `GET /health` → `{ "status": "ok" }`  
Interactive docs: `http://localhost:8000/docs`

Point the mobile app at this server:

```env
# hookup-app/.env.local
EXPO_PUBLIC_API_HOST=localhost:8000
EXPO_PUBLIC_USE_MOCK_API=false
EXPO_PUBLIC_USE_MOCK_WS=false
```

## Architecture

| Layer | Location | Notes |
|-------|----------|-------|
| Entry | `main.py` | CORS, routers, `/ws/chat` |
| Store | `app/store.py` | In-memory data (demo); caps mirror mobile memory limits |
| Auth | `app/routers/auth.py`, `app/auth.py` | JWT, bcrypt, rate limits, WS tickets |
| WebSocket | `app/websocket.py` | Membership checks, 64 KB message limit, block enforcement |
| Admin | `app/routers/admin.py` | Suspend/ban, reports, content, audit log |
| Push | `app/push_dispatch.py` | Expo Push API (best-effort; requires device tokens) |
| Config | `app/config.py` | Env-based settings; fails startup if default JWT secret in production |

## Environment variables

Copy `.env.example` to `.env`. Never commit real secrets.

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | *(dev default)* | **Required** when `DEV_MODE=false` |
| `DEV_MODE` | `true` | When `false`, hides password-reset demo codes and enforces JWT secret |
| `JWT_EXPIRE_HOURS` | `168` | Access token lifetime |
| `CORS_ORIGINS` | `*` | Comma-separated allowlist; use explicit origins in production |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |
| `S3_BUCKET` | — | Optional; blank = mock presigned uploads |
| `S3_REGION` | `eu-west-1` | S3 region |
| `S3_PUBLIC_BASE_URL` | — | Public CDN/base URL for uploaded media |
| `ADMIN_EMAIL` | — | Admin login email |
| `ADMIN_PASSWORD_HASH` | — | bcrypt hash for admin password |
| `ADMIN_JWT_EXPIRE_HOURS` | `8` | Admin session length |
| `ADMIN_LOGIN_RATE_LIMIT` | `10` | Max admin login attempts per window |
| `ADMIN_LOGIN_RATE_WINDOW_SECONDS` | `300` | Rate-limit window |

Generate an admin password hash:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'your-secure-password', bcrypt.gensalt()).decode())"
```

## API overview

### Auth — `/auth`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Register (min 8-char password, `birthDate`, age derived server-side) |
| POST | `/auth/login` | Login (unknown emails → 401) |
| POST | `/auth/social` | Social login stub |
| POST | `/auth/ws-ticket` | **Bearer required** — short-lived WebSocket ticket (60s) |
| POST | `/auth/forgot-password` | Request reset (`demoCode` only when `DEV_MODE=true`) |
| POST | `/auth/reset-password` | Reset with code |
| POST | `/auth/change-password` | Change password (authenticated) |
| DELETE | `/auth/account` | Full account erasure |
| POST | `/auth/change-email` | Change email |
| POST | `/auth/verify-email` | Verify email code |

Auth routes are rate-limited (10 requests / 5 minutes / IP).

### Users — `/users`

Profile, nearby discovery (geohash + visibility rules), likes/taps/views, consents, data export, push token.

| Method | Path | Description |
|--------|------|-------------|
| GET/PATCH | `/users/me` | Current user / update profile |
| PATCH | `/users/me/push-token` | Register Expo push token |
| POST | `/users/me/consents` | Record terms/privacy consent |
| POST | `/users/me/data-export` | Queue GDPR-style export |
| GET | `/users/me/data-export/{id}` | Export status |
| GET | `/users/nearby` | Discovery with filters |
| GET | `/users/{id}` | Public profile (coordinate + NSFW redaction) |

Actor IDs are derived from JWT — client-supplied `viewerId` / `actorUserId` are ignored.

### Conversations — `/conversations`, `/messages`

REST for inbox bootstrap and history. **Sending messages is WebSocket-only.**

### Misc — `/settings`, `/blocks`, `/reports`, `/notifications`, `/uploads`, `/moderation`

- `POST /notifications` is **server-only** (403 from clients)
- `GET /reports` returns only the authenticated reporter's reports
- Block list, favorites, touch analytics, media presign + scan

### Admin — `/admin`

Requires admin JWT from `POST /admin/auth/login`.

- User moderation: suspend, ban, unsuspend
- Reports queue with filtering
- Content moderation
- Audit log (append-only, capped at 500 entries)

### Events — `/events`

Event CRUD and RSVP (tab hidden in production mobile builds; routes remain for dev).

## WebSocket — `/ws/chat`

Connect with a **short-lived ticket** (preferred):

1. `POST /auth/ws-ticket` with `Authorization: Bearer <jwt>`
2. Connect: `ws://localhost:8000/ws/chat?ticket=<ticket>`

Legacy `?token=<jwt>` is still accepted but discouraged.

### Security

- Conversation membership verified before send/read/typing
- Blocked participants cannot send messages (`API_006`)
- Max message size: 64 KB
- Push dispatch on new messages (Expo tokens)

### Client events

`message.send`, `typing.start/stop`, `message.read`, `message.viewed`, `ping`

### Server events

`message.new`, `message.ack`, `typing.*`, `presence.update`, `pong`, `error`

See [hookup-app/docs/API_CONTRACT.md](../hookup-app/docs/API_CONTRACT.md) for full event schemas.

## Privacy & data protection

- **Coordinate redaction**: non-owners see geohash centroid when location sharing is on; coords stripped when off
- **Profile visibility**: `hidden`, `nearby`, `everyone` enforced server-side
- **Blocks**: mutual block on messaging, profile views, likes, taps, conversation creation
- **NSFW albums**: media URLs omitted for non-owners; `locked: true` flag
- **Media uploads**: filename, MIME, extension, and size validation before presign

## Compliance (SOC 2-oriented)

- Consent audit trail (`POST /users/me/consents`)
- Data export requests with audit logging
- Full account deletion (profile, messages, blocks, favorites, notifications; reports anonymized)
- User audit events: login, register, delete, export, consent, report, block
- Report reasons include `underage`; details capped at 500 chars

## Data caps (in-memory store)

| Resource | Cap |
|----------|-----|
| Messages per conversation | 100 |
| Profile views / likes | 200 each |
| Notifications | 80 |
| Reports | 50 |
| Audit logs | 500 |

## Push notifications

When a user registers an Expo push token via `PATCH /users/me/push-token`, the backend dispatches pushes on:

- New chat messages
- Profile likes
- Profile taps

Production requires EAS/APNs/FCM credentials configured in Expo — not stored in this repo.

## Production checklist

- [ ] Set `DEV_MODE=false` and a strong `JWT_SECRET`
- [ ] Set explicit `CORS_ORIGINS` (no `*` with credentials)
- [ ] Configure `ADMIN_EMAIL` + `ADMIN_PASSWORD_HASH`
- [ ] Replace in-memory store with Postgres (out of scope for demo)
- [ ] Wire real CSAM/NSFW classifier at `scan_media()` integration point
- [ ] Configure S3 presign for media uploads

## Development

```bash
# Run with auto-reload
python main.py

# Or explicitly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Verify imports:

```bash
python -c "from app.models import WsTicketResponse; from app.websocket import chat_manager; print('ok')"
```

## Related docs

- [Mobile app README](../hookup-app/README.md)
- [API contract (shared)](../hookup-app/docs/API_CONTRACT.md)
