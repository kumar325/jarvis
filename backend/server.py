"""FastAPI backend wrapping ask_jarvis() with a WebSocket endpoint for the HUD frontend.

Run from the project root: uvicorn backend.server:app --reload
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Use Windows certificate store so httpx (Groq, Hugging Face) can verify TLS on this
# machine — same fix jarvis.py applies; needed here too since this is a separate entrypoint.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from agent_loop import ask_jarvis

from . import state
from .ws_messages import (
    AssistantTextMessage,
    ErrorMessage,
    ToolCallMessage,
    ToolResultMessage,
    UserTextMessage,
    VitalsUpdateMessage,
)

app = FastAPI(title="Jarvis HUD backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/vitals")
def get_vitals():
    return {"vitals": state.get_vitals()}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json(VitalsUpdateMessage(vitals=state.get_vitals()).model_dump())

    try:
        while True:
            raw = await websocket.receive_json()
            try:
                incoming = UserTextMessage.model_validate(raw)
            except ValidationError:
                await websocket.send_json(
                    ErrorMessage(message="expected a user_text message").model_dump()
                )
                continue

            user_text = incoming.text.strip()
            if not user_text:
                continue

            loop = asyncio.get_running_loop()

            def on_event(event: dict):
                # Runs on the threadpool worker thread — hop back onto the event loop to send.
                if event.get("type") == "tool_call":
                    payload = ToolCallMessage.model_validate(event).model_dump()
                elif event.get("type") == "tool_result":
                    payload = ToolResultMessage.model_validate(event).model_dump()
                else:
                    payload = event
                future = asyncio.run_coroutine_threadsafe(websocket.send_json(payload), loop)
                future.add_done_callback(lambda f: f.exception())

            try:
                reply = await run_in_threadpool(ask_jarvis, user_text, on_event)
            except Exception as e:
                await websocket.send_json(ErrorMessage(message=str(e)).model_dump())
                continue

            state.record_turn()
            await websocket.send_json(AssistantTextMessage(text=reply).model_dump())
            await websocket.send_json(VitalsUpdateMessage(vitals=state.get_vitals()).model_dump())
    except WebSocketDisconnect:
        pass
