"""FastAPI backend wrapping ask_jarvis() with a WebSocket endpoint for the HUD frontend.

Run from the project root: uvicorn backend.server:app --reload
"""
import asyncio
import json
import os
import re
import sys
import uuid
from datetime import datetime
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

# Collected on the web path so a browser study session produces the same on-disk state a
# jarvis.py CLI session does. Write path ONLY — neither file is read back into the system
# prompt (see system_prompt.py and CLAUDE.md's "Personalization layers"): re-injecting them
# would be a second personalization channel and would make an Arch 2 result impossible to
# attribute to the cold-start profile alone.
#
# Imported at module level rather than lazily inside the handlers so the cost lands at
# backend startup, before a participant sits down. It adds nothing new anyway — backend
# .state already imports preferences transitively, so the embedder is loaded either way.
from preferences import save_pref
from style_tracker import record_utterance

from . import audio, ratings, state
from .ws_messages import (
    AssistantTextMessage,
    DirectivesUpdateMessage,
    DocumentsUpdateMessage,
    ErrorMessage,
    RatingMessage,
    SessionInfoMessage,
    SetTtsMessage,
    ToolCallMessage,
    ToolResultMessage,
    TranscriptMessage,
    TtsStateMessage,
    UserTextMessage,
    VitalsUpdateMessage,
)

app = FastAPI(title="Jarvis HUD backend")

# Vite picks the next free port when 5173 is taken, so both are allowed. (Only the REST
# endpoints below are affected — browsers don't apply CORS to WebSocket handshakes.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Which arm of the study this process is serving (jarvis_sandbox/architecture.txt:
# arch1 = generic baseline, arch2 = URL cold-start personalization), recorded on every
# rating so the two phases can be told apart at analysis time. Set it when launching:
#   $env:JARVIS_STUDY_CONDITION = "arch1"   (or "arch2")
# Left "unspecified" rather than guessing a default — an unlabeled rating is obvious in
# the log, a wrongly-labeled one is not.
STUDY_CONDITION = os.environ.get("JARVIS_STUDY_CONDITION", "unspecified")

# Pseudonymous participant code (P01, P02, ...), matching reset_user_state.py's
# --participant labels. This is what joins one participant's arch1 ratings to their arch2
# ratings when the two arms run on separate machines writing separate log files — session
# ids are per-connection and can't do it. Deliberately a code, not a name: the protocol
# keeps identity separate from task responses, so the code-to-person mapping lives outside
# this repo.
PARTICIPANT_ID = os.environ.get("JARVIS_PARTICIPANT_ID", "unassigned")

# Printed to the operator's terminal (never to the participant's screen) so a mislabeled
# session is caught before it's run rather than found at analysis time.
print(
    f"[jarvis] study condition={STUDY_CONDITION} participant={PARTICIPANT_ID} "
    f"-> {ratings.RATINGS_PATH.relative_to(Path(__file__).resolve().parent.parent)}",
    flush=True,
)


def log_operator(message: str):
    """Warn the session runner on their own terminal, never the participant's screen.

    Deliberately not an ErrorMessage: the frontend renders those into the participant's
    conversation AND calls setBusy(false) (frontend/src/hooks/useJarvisSocket.ts's "error"
    case), so using one mid-turn would both show a stray line and unlock the input while
    ask_jarvis is still running. Study-data capture failing is an operator problem — it
    must not change what the participant sees or can do.
    """
    print(f"[jarvis] {message}", flush=True)


# Bounds the per-connection pending-exchange map. Ratings are mandatory in the UI, so in
# practice at most one exchange is ever awaiting a rating; this only matters if a
# participant refreshes mid-session and leaves stale entries behind.
MAX_PENDING_EXCHANGES = 50


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

    # One session per connection, matching the fresh-conversation reset above. Carries no
    # participant identity — it exists purely to group this session's ratings.
    session_id = f"sesn_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
    turn_index = 0
    message_counter = 0
    # message_id -> the exchange it belongs to, kept until that response is rated.
    pending_exchanges: dict[str, dict] = {}

    def next_message_id() -> str:
        nonlocal message_counter
        message_counter += 1
        return f"{session_id}_msg{message_counter:03d}"

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

    await send_json_safe(
        SessionInfoMessage(session_id=session_id, condition=STUDY_CONDITION).model_dump()
    )
    await send_json_safe(TtsStateMessage(enabled=tts_enabled).model_dump())
    await send_state_snapshot()

    def register_exchange(message_id: str, user_text: str, reply: str, input_mode: str):
        """Remember what a response was answering, so an incoming rating can be logged
        against the actual exchange rather than just an id."""
        if len(pending_exchanges) >= MAX_PENDING_EXCHANGES:
            pending_exchanges.pop(next(iter(pending_exchanges)))
        pending_exchanges[message_id] = {
            "turn_index": turn_index,
            "input_mode": input_mode,
            "user_text": user_text,
            "assistant_text": reply,
            "responded_at": ratings.utc_now_iso(),
        }

    async def handle_user_text(user_text: str, input_mode: str = "text"):
        nonlocal busy, tts_enabled, turn_index
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
                # ratable=False: a mute confirmation isn't model output, so the UI must not
                # demand a thumbs up/down on it.
                await send_json_safe(
                    AssistantTextMessage(
                        text=reply, id=next_message_id(), ratable=False
                    ).model_dump()
                )
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

        # Mirrors jarvis.py's record_utterance() call, so a browser session fills the
        # style buffer the same way a CLI session does. Two deliberate differences:
        #   - Placed AFTER the parse_tts_command guard above. The CLI records every input
        #     before it branches, so "mute"/"talk off" land in its buffer; those are
        #     control phrases, not speech samples worth mirroring, so they never reach the
        #     buffer here.
        #   - Threadpooled, because every ANALYSIS_INTERVAL-th call invokes the Groq LLM
        #     (LLM_TIMEOUT_S=20) and would otherwise block the event loop mid-session.
        try:
            await run_in_threadpool(record_utterance, user_text)
        except Exception as e:
            # Capture is study data collection, not part of answering the participant —
            # a failure here must never cost them their turn.
            log_operator(f"failed to record utterance for style buffer: {e}")

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
            turn_index += 1
            message_id = next_message_id()
            register_exchange(message_id, user_text, reply, input_mode)
            await send_json_safe(
                AssistantTextMessage(text=reply, id=message_id, ratable=True).model_dump()
            )

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

    async def handle_set_tts(enabled: bool):
        nonlocal tts_enabled
        tts_enabled = enabled
        # Echoed back so the UI's toggle reflects server state, exactly as the spoken
        # "talk off" path does.
        await send_json_safe(TtsStateMessage(enabled=tts_enabled).model_dump())

    async def handle_rating(incoming: RatingMessage):
        exchange = pending_exchanges.pop(incoming.message_id, None)
        if exchange is None:
            # Unknown id — a stale tab, or a rating replayed after a reconnect. Better to
            # say so than to write a half-empty row into the study log.
            await send_json_safe(
                ErrorMessage(message="that response is no longer awaiting a rating").model_dump()
            )
            return

        record = {
            "session_id": session_id,
            "participant_id": PARTICIPANT_ID,
            "condition": STUDY_CONDITION,
            "message_id": incoming.message_id,
            "rating": incoming.rating,
            "rated_at": ratings.utc_now_iso(),
            **exchange,
        }
        try:
            await run_in_threadpool(ratings.append_rating, record)
        except Exception as e:
            # The UI unblocks optimistically on click and is not told to re-block — a disk
            # error must never strand a participant mid-session. Surfaced so the session
            # runner sees it.
            await send_json_safe(
                ErrorMessage(message=f"failed to log rating: {e}").model_dump()
            )

        # Mirrors jarvis.py's save_pref() calls. Additive to the ratings.jsonl append
        # above, not a replacement: that file stays the study's source of truth (it is the
        # only one carrying participant_id and condition), while preferences.json is the
        # in-context-RLHF pair store the eval harness reads. Independent of the append —
        # if one fails the other still runs.
        try:
            await run_in_threadpool(
                save_pref, exchange["user_text"], exchange["assistant_text"], incoming.rating
            )
        except Exception as e:
            log_operator(f"failed to save preference pair: {e}")

    async def send_busy_error():
        await send_json_safe(
            ErrorMessage(
                message="still processing the previous request — try again in a moment"
            ).model_dump()
        )

    while True:
        try:
            message = await websocket.receive()
        except WebSocketDisconnect:
            break

        if message["type"] == "websocket.disconnect":
            break

        try:
            if message.get("bytes") is not None:
                if busy:
                    await send_busy_error()
                    continue
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
                await handle_user_text(user_text, input_mode="voice")
                continue

            if message.get("text") is None:
                continue

            try:
                payload = json.loads(message["text"])
            except json.JSONDecodeError:
                await send_json_safe(ErrorMessage(message="expected a JSON message").model_dump())
                continue

            kind = payload.get("type")

            # Control messages do no LLM work and deliberately skip the busy guard — a mute
            # press lands mid-reply, and a rating must go through even if the participant
            # has already started the next turn somehow.
            if kind == "set_tts":
                try:
                    await handle_set_tts(SetTtsMessage.model_validate(payload).enabled)
                except ValidationError:
                    await send_json_safe(
                        ErrorMessage(message="malformed set_tts message").model_dump()
                    )
                continue

            if kind == "rating":
                try:
                    await handle_rating(RatingMessage.model_validate(payload))
                except ValidationError:
                    await send_json_safe(
                        ErrorMessage(message="malformed rating message").model_dump()
                    )
                continue

            if busy:
                await send_busy_error()
                continue

            try:
                incoming = UserTextMessage.model_validate(payload)
            except ValidationError:
                await send_json_safe(
                    ErrorMessage(message="expected a user_text message").model_dump()
                )
                continue
            await handle_user_text(incoming.text, input_mode="text")
        except Exception as e:
            # Catch-all so one bad message (transcription glitch, TTS engine hiccup, ...)
            # can never kill the whole connection.
            await send_json_safe(ErrorMessage(message=f"unexpected error: {e}").model_dump())
