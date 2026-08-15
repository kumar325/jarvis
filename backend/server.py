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
from config import PARTICIPANT_ID, STUDY_CONDITION, profile_injection_enabled

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
from speech_summary import summarize_for_speech
from style_tracker import record_utterance
# Read at startup only, to verify the arch2 personalization layer is actually populated —
# this is the same function system_prompt.py injects from, so the check can't drift from
# what the model will really see.
from user_profile import get_profile_summary

from . import audio, ratings, state, tasks
from .ws_messages import (
    AssistantTextMessage,
    DirectivesUpdateMessage,
    DocumentsUpdateMessage,
    ErrorMessage,
    RatingMessage,
    SessionInfoMessage,
    SetTtsMessage,
    TaskCompleteMessage,
    TaskErrorMessage,
    TaskRecordedMessage,
    TaskStateMessage,
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

# Both study labels now live in config.py — system_prompt.py needs the condition too (it
# is what switches the arch1 baseline on), and two modules reading the same env var
# independently is how they drift apart.
#
# Which arm this process serves, and which of the participant's two arms it is. The
# position is derived from the task log rather than taken from a third env var: the
# moderator already has two labels to get right, and order is confounded with architecture
# in a within-subjects design unless it is both counterbalanced at the desk and recorded.
ARCH_POSITION = tasks.arch_position(PARTICIPANT_ID, STUDY_CONDITION)

# Printed to the operator's terminal (never to the participant's screen) so a mislabeled
# session is caught before it's run rather than found at analysis time.
print(
    f"[jarvis] study condition={STUDY_CONDITION} participant={PARTICIPANT_ID} "
    f"arm={ARCH_POSITION} of 2 "
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


# Escape hatch for testing the arch2 wiring without a real participant's URL. Deliberately
# an explicit opt-in: the failure it bypasses is invisible at runtime.
ALLOW_EMPTY_PROFILE = os.environ.get("JARVIS_ALLOW_EMPTY_PROFILE") == "1"


def check_cold_start_profile():
    """Confirm the profile layer matches the arm this process claims to be serving.

    The URL-derived summary is Arch 2's ONLY personalization layer (system_prompt.py), and
    both arms run against the same on-disk state — the profile is seeded once per
    participant and the arm decides whether it is injected. So there are two ways to serve
    a session that is silently the wrong architecture, and neither is visible at runtime:

      arch2 with an empty profile  -> behaves like the arch1 baseline
      arch1 still injecting        -> behaves like arch2

    Both would still stamp their claimed condition on every rating and task row, and
    nothing downstream could detect it afterwards. Hence the check here, before the
    participant sits down.
    """
    if STUDY_CONDITION == "arch1":
        # Not a failure — arch1 is *supposed* to leave a seeded profile untouched, which
        # is exactly why it's worth printing. It's the operator's confirmation that the
        # baseline is really running as a baseline.
        if profile_injection_enabled():
            print(
                "\n  REFUSING TO START: condition is arch1 but profile injection is ON.\n"
                "  config.profile_injection_enabled() and STUDY_CONDITION disagree.\n",
                flush=True,
            )
            raise SystemExit(1)
        try:
            on_disk = len(get_profile_summary().strip())
        except Exception:
            on_disk = 0
        log_operator(
            f"arch1 baseline — profile injection OFF"
            + (f" ({on_disk} chars on disk, deliberately not injected)" if on_disk
               else " (no profile on disk)")
        )
        return

    if STUDY_CONDITION != "arch2":
        return

    try:
        summary = get_profile_summary().strip()
    except Exception as e:
        log_operator(f"could not read user_profile.json: {e}")
        summary = ""

    if summary:
        log_operator(f"cold-start profile loaded ({len(summary)} chars)")
        return

    banner = (
        "\n"
        "  REFUSING TO START: condition is arch2 but the cold-start profile is empty.\n"
        "\n"
        "  Arch 2's only personalization layer is the summary built from the participant's\n"
        "  public URL. Running now would label the session arch2 while behaving like arch1.\n"
        "\n"
        "  Seed it first:\n"
        "    python reset_user_state.py --participant P0X --profile-url https://... -y\n"
        "\n"
        "  Or set JARVIS_ALLOW_EMPTY_PROFILE=1 to run anyway (wiring tests, not participants).\n"
    )
    if ALLOW_EMPTY_PROFILE:
        log_operator("WARNING: arch2 with an EMPTY cold-start profile — "
                     "JARVIS_ALLOW_EMPTY_PROFILE=1 is set, so this is not a participant session")
        return
    print(banner, flush=True)
    raise SystemExit(1)


check_cold_start_profile()


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

    async def send_task_state():
        """Tell the client how far through this arm the participant is.

        Read from the task log rather than held in connection state, so a mid-session
        browser refresh (which starts a whole new connection) resumes at the right task
        instead of showing "Task 1 of 3" again.
        """
        try:
            completed = await run_in_threadpool(
                tasks.count_completed_tasks, PARTICIPANT_ID, STUDY_CONDITION
            )
        except Exception as e:
            log_operator(f"failed to read task log for task state: {e}")
            completed = 0
        await send_json_safe(
            TaskStateMessage(
                completed_tasks=completed,
                next_task=completed + 1,
                arch_complete=completed >= tasks.TASKS_PER_ARCH,
            ).model_dump()
        )

    await send_json_safe(
        SessionInfoMessage(session_id=session_id, condition=STUDY_CONDITION).model_dump()
    )
    await send_json_safe(TtsStateMessage(enabled=tts_enabled).model_dump())
    await send_task_state()
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
                    # Summarized only for the speaker. The full `reply` above is what the
                    # participant reads, what register_exchange() stored, and what a rating
                    # will be logged against — the audio is the only thing shortened.
                    #
                    # Strictly after the AssistantTextMessage: this adds an LLM call before
                    # any sound comes out, and the answer should already be on screen while
                    # it runs. summarize_for_speech() never raises, so a failure here is a
                    # long spoken reply, not a lost turn.
                    spoken = await run_in_threadpool(summarize_for_speech, reply)
                    if spoken != reply:
                        log_operator(
                            f"spoke a summary ({len(reply)} chars -> {len(spoken)})"
                        )
                    audio_reply = await run_in_threadpool(audio.synthesize, spoken)
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
            # Which of the participant's two arms this was. Same reason the survey CSV
            # carries it: order is confounded with architecture in a within-subjects
            # design unless it's recorded.
            "arch_position": ARCH_POSITION,
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

    async def handle_task_complete(_incoming: TaskCompleteMessage):
        """One finished task -> one boundary row in task_events.csv.

        Entirely separate from handle_rating above: that fires on every model response,
        this fires once per task when the moderator marks it finished. They share no state
        and land in different files.

        The three evaluation questions live on a paper worksheet now, so nothing about how
        the task *went* passes through here — only that it ended, and when.
        """
        try:
            task_number = await run_in_threadpool(
                tasks.record_task_complete,
                session_id,
                PARTICIPANT_ID,
                STUDY_CONDITION,
                ARCH_POSITION,
            )
        except Exception as e:
            # Unlike a rating, this is NOT acknowledged optimistically. A rating is one of
            # many and the participant is mid-conversation behind a gate; a boundary is one
            # of three, the moderator is already looking at the screen, and a dropped one
            # shifts the numbering of every task after it — so it's better to leave the
            # button clickable for a retry than to lose the row.
            log_operator(f"failed to record task boundary: {e}")
            await send_json_safe(
                TaskErrorMessage(message=f"could not save the task boundary: {e}").model_dump()
            )
            return

        log_operator(
            f"task complete recorded: participant={PARTICIPANT_ID} arch={STUDY_CONDITION} "
            f"arm={ARCH_POSITION} task={task_number} -> {tasks.TASK_EVENTS_PATH.name}"
        )
        await send_json_safe(
            TaskRecordedMessage(
                task_number=task_number,
                next_task=task_number + 1,
                arch_complete=task_number >= tasks.TASKS_PER_ARCH,
            ).model_dump()
        )

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

            if kind == "task_complete":
                try:
                    await handle_task_complete(TaskCompleteMessage.model_validate(payload))
                except ValidationError as e:
                    # A task_error rather than an ErrorMessage: this never belongs in the
                    # participant's transcript, and the button needs to become clickable
                    # again.
                    log_operator(f"malformed task complete message: {e}")
                    await send_json_safe(
                        TaskErrorMessage(
                            message="the task message didn't validate — try again"
                        ).model_dump()
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
