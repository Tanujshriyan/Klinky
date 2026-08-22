from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, validate_settings
from app.errors import ApiError, api_error_handler
from app.routers import admin, auth, conversations, events, misc, users
from app.websocket import chat_websocket

validate_settings()

app = FastAPI(title="Pulse API", version="1.0.0")

allow_all_origins = settings.cors_origins == "*"
origins = ["*"] if allow_all_origins else [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(ApiError, api_error_handler)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(conversations.router)
app.include_router(events.router)
app.include_router(misc.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket, token: str | None = None, ticket: str | None = None):
    await chat_websocket(websocket, token, ticket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
