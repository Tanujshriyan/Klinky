# Pulse

Location-based discovery and messaging platform — **Expo mobile/web client** + **FastAPI backend**.

## Repository layout

| Path | Description |
|------|-------------|
| [`hookup-app/`](./hookup-app/) | Expo SDK 57 app (iOS, Android, web) |
| [`backend/`](./backend/) | FastAPI REST + WebSocket API |

## Quick start

**Demo mode (no backend):**

```bash
cd hookup-app
npm install
npm start
```

Press `w` for web.

**With live backend:**

```bash
# Terminal 1
cd backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python main.py

# Terminal 2
cd hookup-app
npm install
cp .env.example .env.local
# Edit .env.local: EXPO_PUBLIC_USE_MOCK_API=false, EXPO_PUBLIC_USE_MOCK_WS=false
npm start
```

## Documentation

- [Mobile app README](./hookup-app/README.md) — screens, env vars, auth, privacy, push
- [Backend README](./backend/README.md) — API routes, admin, security, compliance
- [API contract](./hookup-app/docs/API_CONTRACT.md) — shared REST + WebSocket schemas

## Features

- 18+ registration with birth-date gate and terms consent audit trail
- Geohash-based nearby discovery with privacy redaction and block enforcement
- Real-time chat (WebSocket tickets, membership checks, message caps)
- Admin moderation (suspend/ban, reports, audit log)
- Compliance APIs (data export, account deletion, consent logging)
- Push notifications (local + Expo remote dispatch)
- SOC 2-oriented security hardening (SecureStore JWT, rate limits, CORS)

## License

Private — demo / development use.
