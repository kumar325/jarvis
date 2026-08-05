"""FastAPI backend wrapping ask_jarvis() with a WebSocket endpoint for the HUD frontend.

Run from the project root: uvicorn backend.server:app --reload
"""
import asyncio
import json
import re
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

from agent_loop import ask_jarvis, clear_conversation

from . import audio, state
from .ws_messages import (
    AssistantTextMessage,
    DirectivesUpdateMessage,
    DocumentsUpdateMessage,
    ErrorMessage,
    ToolCallMessage,
    ToolResultMessage,
    TranscriptMessage,
    TtsStateMessage,
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


@app.get("/directives")
def get_directives():
    return {"directives": state.get_directives()}


@app.get("/documents")
def get_documents():
    return {"documents": state.get_documents()}


# Matched against normalized (lowercased, trailing punctuation stripped) user text,
# spoken or typed, to toggle TTS without spending an ask_jarvis()/LLM call on it.
# Word-boundary regexes so e.g. "unmute" doesn't also match the "mute" pattern.
# Keep in sync with frontend/src/lib/ttsCommand.ts's client-side mirror.
_UNMUTE_PATTERNS = [
    r"\btalk on\b", r"\bstart talking\b", r"\bunmute\b", r"\bspeak up\b",
    r"\bvoice on\b", r"\bturn on (the )?voice\b",
]
_MUTE_PATTERNS = [
    r"\btalk off\b", r"\bstop talking\b", r"\bmute\b", r"\bbe quiet\b", r"\bgo silent\b",
    r"\bvoice off\b", r"\bturn off (the )?voice\b",
]


def parse_tts_command(text: str) -> bool | None:
    """Returns True for an unmute command, False for a mute command, None if the text
    isn't a TTS toggle at all."""
    normalized = text.strip().lower().rstrip(".!?")
    if any(re.search(p, normalized) for p in _UNMUTE_PATTERNS):
        return True
    if any(re.search(p, normalized) for p in _MUTE_PATTERNS):
        return False
    return None


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Every connection starts a fresh session. agent_loop.conversation is module-level
    # and lives as long as the process, so without this the previous participant's full
    # transcript would still be in context after a user-state reset. Consequences worth
    # knowing: a mid-session browser refresh starts the conversation over, and a second
    # tab wipes the first tab's history (the backend assumes one client at a time).
    clear_conversation()

    # Serializes every send on this connection — tool-event sends (scheduled from a
    # worker thread via run_coroutine_threadsafe) and the main reply flow must never
    # write to the socket concurrently, or frames can interleave and corrupt the stream.
    send_lock = asyncio.Lock()
    busy = False
    tts_enabled = True

    async def send_json_safe(payload: dict) -> bool:
        try:
            async with send_lock:
                await websocket.send_json(payload)
            return True
        except Exception:
            return False

    async def send_bytes_safe(payload: bytes) -> bool:
        try:
            async with send_lock:
                await websocket.send_bytes(payload)
            return True
        except Exception:
            return False

    async def send_state_snapshot():
        await send_json_safe(VitalsUpdateMessage(vitals=state.get_vitals()).model_dump())
        await send_json_safe(DirectivesUpdateMessage(directives=state.get_directives()).model_dump())
        await send_json_safe(DocumentsUpdateMessage(documents=state.get_documents()).model_dump())

    await send_state_snapshot()

    async def handle_user_text(user_text: str):
        nonlocal busy, tts_enabled
        user_text = user_text.strip()
        if not user_text:
            return

        tts_command = parse_tts_command(user_text)
        if tts_command is not None:
            # Intercepted before ask_jarvis() — a mute/unmute toggle isn't a real query,
            # so it never touches the LLM.
            tts_enabled = tts_command
            reply = "Voice output back on." if tts_enabled else "Voice output off — I'll keep replying in text."
            busy = True
            try:
                await send_json_safe(TtsStateMessage(enabled=tts_enabled).model_dump())
                await send_json_safe(AssistantTextMessage(text=reply).model_dump())
                if tts_enabled:
                    try:
                        audio_reply = await run_in_threadpool(audio.synthesize, reply)
                        await send_bytes_safe(audio_reply)
                    except Exception as e:
                        await send_json_safe(
                            ErrorMessage(message=f"speech synthesis failed: {e}").model_dump()
                        )
            finally:
                busy = False
            return

        loop = asyncio.get_running_loop()

        def on_event(event: dict):
            # Runs on the threadpool worker thread — hop back onto the event loop to send.
            if event.get("type") == "tool_call":
                payload = ToolCallMessage.model_validate(event).model_dump()
            elif event.get("type") == "tool_result":
                payload = ToolResultMessage.model_validate(event).model_dump()
            else:
                payload = event
            future = asyncio.run_coroutine_threadsafe(send_json_safe(payload), loop)
            future.add_done_callback(lambda f: f.exception())

        busy = True
        try:
            try:
                reply = await run_in_threadpool(ask_jarvis, user_text, on_event)
            except Exception as e:
                await send_json_safe(ErrorMessage(message=str(e)).model_dump())
                return

            state.record_turn()
            await send_json_safe(AssistantTextMessage(text=reply).model_dump())

            if tts_enabled:
                try:
                    audio_reply = await run_in_threadpool(audio.synthesize, reply)
                    await send_bytes_safe(audio_reply)
                except Exception as e:
                    await send_json_safe(
                        ErrorMessage(message=f"speech synthesis failed: {e}").model_dump()
                    )

            await send_state_snapshot()
        finally:
            # Always released, even if ask_jarvis/synthesis raised something unexpected —
            # otherwise a single failure would permanently lock out this connection.
            busy = False

    while True:
        try:
            message = await websocket.receive()
        except WebSocketDisconnect:
            break

        if message["type"] == "websocket.disconnect":
            break

        if busy:
            await send_json_safe(
                ErrorMessage(
                    message="still processing the previous request — try again in a moment"
                ).model_dump()
            )
            continue

        try:
            if message.get("bytes") is not None:
                try:
                    user_text = await run_in_threadpool(audio.transcribe_bytes, message["bytes"])
                except Exception as e:
                    await send_json_safe(
                        ErrorMessage(message=f"transcription failed: {e}").model_dump()
                    )
                    continue
                if not user_text.strip():
                    await send_json_safe(
                        ErrorMessage(message="couldn't hear anything in that recording").model_dump()
                    )
                    continue
                await send_json_safe(TranscriptMessage(text=user_text).model_dump())
                await handle_user_text(user_text)

            elif message.get("text") is not None:
                try:
                    incoming = UserTextMessage.model_validate(json.loads(message["text"]))
                except (ValidationError, json.JSONDecodeError):
                    await send_json_safe(
                        ErrorMessage(message="expected a user_text message").model_dump()
                    )
                    continue
                await handle_user_text(incoming.text)
        except Exception as e:
            # Catch-all so one bad message (transcription glitch, TTS engine hiccup, ...)
            # can never kill the whole connection.
            await send_json_safe(ErrorMessage(message=f"unexpected error: {e}").model_dump())
