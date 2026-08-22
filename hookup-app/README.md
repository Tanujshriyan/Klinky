# Pulse — Mobile App (Expo)

Location-based discovery and messaging app built with **Expo SDK 57**, **React Native**, and **expo-router**. Supports iOS, Android, and web.

Pair with the [FastAPI backend](../backend/README.md) for live API + WebSocket, or run fully offline in **demo mode** (default).

## Quick start (demo mode)

```bash
cd hookup-app
npm install
npm start
```

| Key | Action |
|-----|--------|
| `w` | Open web |
| `a` | Android emulator |
| `i` | iOS simulator (macOS) |
| QR | Expo Go on device |

Demo mode uses in-memory mock API and mock WebSocket — no backend required.

## Quick start (live backend)

**Terminal 1 — API**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env
python main.py
```

**Terminal 2 — Mobile**

```bash
cd hookup-app
cp .env.example .env.local
```

Set in `.env.local`:

```env
EXPO_PUBLIC_API_HOST=localhost:8000
EXPO_PUBLIC_USE_MOCK_API=false
EXPO_PUBLIC_USE_MOCK_WS=false
```

```bash
npm start
```

On a physical device, replace `localhost` with your machine's LAN IP (e.g. `192.168.1.10:8000`).

## Auth flow

1. **Register** — birth-date picker enforces 18+; terms acceptance required
2. **Accept terms** — Terms, Privacy Policy, and Community Guidelines (links in screen)
3. **Onboarding** — profile setup (photos, bio, birth date for social logins)
4. **Sign in** — email/password or social (Google, Facebook, Apple on iOS)

| Scenario | Behavior |
|----------|----------|
| New email (demo) | Auto-creates session |
| Registered email | Requires saved password |
| `fail@example.com` | Always fails (`AUTH_001`) |
| Social login | Routes through onboarding for birth date |
| Forgot password | Reset code shown only in `__DEV__` builds |

**Security:** JWT stored in `expo-secure-store` (native) or session storage (web). Logout wipes auth, settings, blocked list, and favorites from AsyncStorage.

## Screens

| Tab | Route | Description |
|-----|-------|-------------|
| Nearby | `/(tabs)` | 3-column profile grid, filters, geohash distances |
| Map | `/(tabs)/map` | Map pins + bottom sheet (native) / list (web) |
| Messages | `/(tabs)/messages` | Inbox with live WebSocket updates |
| Profile | `/(tabs)/profile` | Own profile + settings |

**Stack:** chat, user profiles, favorites, filters modal, settings, notifications, album viewer.

**Hidden in production:** Events tab and event deep links are gated behind `__DEV__`. Event stack routes remain for development.

**Deep links** (`hookupapp://`): `user/<id>`, `chat/<id>` (no event links in production).

## Real-time chat

| Mode | Client | When |
|------|--------|------|
| Demo | `MockWebSocketClient` | `EXPO_PUBLIC_USE_MOCK_WS=true` (default) |
| Live | `ChatWebSocketClient` | `EXPO_PUBLIC_USE_MOCK_WS=false` |

Live mode:

1. Fetches short-lived ticket via `POST /auth/ws-ticket`
2. Connects to `ws://<host>/ws/chat?ticket=...`
3. Optimistic send, ack, typing, presence, failed-message retry

Messages are trimmed to **100 per conversation** in memory. Chat list uses **FlashList** virtualization.

## Privacy & settings

**Settings → Privacy**

- Profile visibility: Everyone / Nearby / Hidden
- Approximate location (geohash ~1 km), hide distance, show on map
- Online status toggle
- Block list
- Data export request (wired to backend compliance API)
- Account deletion (password confirmation required)

**Web:** cookie consent banner; push toggle hidden on web.

**Pre-permission:** location rationale modal before OS prompt; notification permission on native.

## Push notifications (native)

- Local inbox + device alerts when not in active chat
- Tap routing to chat or user profile
- Remote push: registers Expo token via `PATCH /users/me/push-token`
- Requires EAS build + APNs/FCM credentials for production delivery

## Environment variables

Copy `.env.example` to `.env.local`. **Never put secrets, AWS keys, or private tokens here** — public Expo vars only.

| Variable | Default | Description |
|----------|---------|-------------|
| `EXPO_PUBLIC_API_HOST` | `localhost:8000` | Backend host |
| `EXPO_PUBLIC_API_PROTOCOL` | `http` on localhost | REST/WS scheme |
| `EXPO_PUBLIC_USE_MOCK_API` | `true` | In-memory `MockApiService` |
| `EXPO_PUBLIC_USE_MOCK_WS` | `true` | Simulated WebSocket |
| `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID` | — | Google OAuth (web) |
| `EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID` | — | Google OAuth (iOS) |
| `EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID` | — | Google OAuth (Android) |
| `EXPO_PUBLIC_FACEBOOK_APP_ID` | — | Facebook login |
| `EXPO_PUBLIC_S3_PRESIGN_URL` | — | Optional custom presign endpoint |
| `EXPO_PUBLIC_S3_BUCKET` | — | Display label only |
| `EXPO_PUBLIC_S3_REGION` | — | Display label only |
| `EXPO_PUBLIC_S3_PUBLIC_BASE_URL` | — | Public media base URL |
| `GOOGLE_MAPS_API_KEY` | — | Native maps (via `app.config.ts`) |

## Project structure

```
hookup-app/
├── app/                    # expo-router screens
│   ├── (auth)/             # login, register, terms, onboarding
│   ├── (tabs)/             # nearby, map, messages, profile
│   ├── chat/               # conversation screen
│   └── settings/           # privacy, account, notifications, legal
├── src/
│   ├── components/         # UI, UserCard, MessageBubble, legal modals
│   ├── constants/          # legalContent, privacy, reportReasons
│   ├── services/
│   │   ├── api/            # ApiClient interface + types
│   │   ├── http/           # HttpApiService (live backend)
│   │   ├── mock/           # MockApiService + mockAuth (dev only)
│   │   ├── websocket/      # ChatWebSocketClient + wsAuth
│   │   └── secureTokenStorage.ts
│   ├── store/              # zustand: auth, chat, settings, safety
│   └── utils/              # geohash, memory caps, pickChatMedia
└── docs/API_CONTRACT.md    # Shared REST + WS contract
```

## Memory & performance

Defined in `src/utils/memory.ts`:

| Constant | Value |
|----------|-------|
| Messages per conversation | 100 |
| Message page size | 20 |
| Max pick image edge | 1920 px |
| Pick image quality | 0.8 |

Chat media uses `expo-image-manipulator` for native resize. Images use `resizeMethod="resize"`. Web blob URLs are revoked after upload.

## Legal & compliance

Shared copy in `src/constants/legalContent.ts`:

- Terms of Service, Privacy Policy, Community Guidelines
- Cookie/tracking section (web)
- Data export and account deletion in Settings

Consent recorded via `POST /users/me/consents` when accepting terms.

## Scripts

```bash
npm start          # Expo dev server
npm run web        # Web only
npm run android    # Android
npm run ios        # iOS (macOS)
npx tsc --noEmit   # Type check
```

## Production checklist

- [ ] Set `EXPO_PUBLIC_USE_MOCK_API=false` and `EXPO_PUBLIC_USE_MOCK_WS=false`
- [ ] Point `EXPO_PUBLIC_API_HOST` at production API (HTTPS)
- [ ] Configure EAS credentials for push (APNs + FCM)
- [ ] Set OAuth client IDs for social login
- [ ] Set `GOOGLE_MAPS_API_KEY` for native maps
- [ ] Backend: `DEV_MODE=false`, strong `JWT_SECRET`, explicit CORS

## Related docs

- [Backend README](../backend/README.md)
- [API contract](./docs/API_CONTRACT.md)

## Demo extras

Pulse+ / boosts, travel cities, favorites, group chats, mock calls, report flow, filename safety scan (blocks names containing `illegal`). Premium and call screens show demo-mode banners.
