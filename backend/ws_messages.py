"""Typed schemas for the WebSocket message contract between the HUD frontend and this backend."""
from typing import Any, Literal
from pydantic import BaseModel


class UserTextMessage(BaseModel):
    """Client -> server: a text query to run through ask_jarvis()."""
    type: Literal["user_text"] = "user_text"
    text: str


class SetTtsMessage(BaseModel):
    """Client -> server: mute/unmute voice output from the UI toggle. Mirrors what the
    spoken/typed 'talk off' command does, so both paths land on the same server state."""
    type: Literal["set_tts"] = "set_tts"
    enabled: bool


class RatingMessage(BaseModel):
    """Client -> server: the participant's thumbs up/down on one assistant response.
    `message_id` is the id the server put on that AssistantTextMessage."""
    type: Literal["rating"] = "rating"
    message_id: str
    rating: Literal["up", "down"]


class TaskCompleteMessage(BaseModel):
    """Client -> server: the moderator has marked a task finished.

    Carries nothing but its own type. The three evaluation questions are answered on a
    paper worksheet now, so this records only the boundary — and deliberately carries no
    task number either, since the server derives that from the log so a browser refresh
    can't restart the count (see tasks.record_task_complete).
    """
    type: Literal["task_complete"] = "task_complete"


class TaskStateMessage(BaseModel):
    """Server -> client: how far through this arm the participant is, sent on connect.

    Lets a refreshed browser pick the task counter back up from the log instead of showing
    "Task 1 of 3" again after two tasks are already done.
    """
    type: Literal["task_state"] = "task_state"
    completed_tasks: int
    next_task: int
    arch_complete: bool


class TaskRecordedMessage(BaseModel):
    """Server -> client: a task boundary reached disk. This is the frontend's cue to take
    the Finish Task button out of its pending state — sent only after the append succeeds,
    so a failed write leaves the button clickable for a retry rather than silently dropping
    the boundary and shifting every later task number."""
    type: Literal["task_recorded"] = "task_recorded"
    task_number: int
    next_task: int
    arch_complete: bool


class TaskErrorMessage(BaseModel):
    """Server -> client: the task boundary could not be written.

    A distinct type from ErrorMessage because the frontend renders those into the
    participant's conversation log; a disk problem is an operator concern and belongs on
    the moderator's own control, not in the participant's transcript.
    """
    type: Literal["task_error"] = "task_error"
    message: str


class SessionInfoMessage(BaseModel):
    """Server -> client: identifiers for this session, sent once on connect. The frontend
    only displays nothing with these — they exist so ratings can be tied back to a session."""
    type: Literal["session_info"] = "session_info"
    session_id: str
    condition: str


class AssistantTextMessage(BaseModel):
    """Server -> client: one assistant turn.

    `ratable` is False for replies that aren't model output (mute/unmute confirmations),
    so the UI doesn't demand a thumbs up/down on them and pollute the ratings log.
    """
    type: Literal["assistant_text"] = "assistant_text"
    text: str
    id: str
    ratable: bool = True


class TranscriptMessage(BaseModel):
    """Server -> client: what a voice recording was transcribed to, so the frontend can
    show it as the user's turn in the wire log (it never sees the audio's text otherwise)."""
    type: Literal["transcript"] = "transcript"
    text: str


class ToolCallMessage(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str
    tool_name: str
    args: dict[str, Any]


class ToolResultMessage(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    id: str
    tool_name: str
    preview: str


class VitalsUpdateMessage(BaseModel):
    type: Literal["vitals_update"] = "vitals_update"
    vitals: list[dict[str, Any]]


class DirectivesUpdateMessage(BaseModel):
    type: Literal["directives_update"] = "directives_update"
    directives: list[dict[str, Any]]


class DocumentsUpdateMessage(BaseModel):
    type: Literal["documents_update"] = "documents_update"
    documents: list[dict[str, Any]]


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str


class TtsStateMessage(BaseModel):
    """Server -> client: TTS mute state changed (via a 'talk off'/'talk on' voice
    command), so the frontend can sync its ttsEnabled toggle and indicator."""
    type: Literal["tts_state"] = "tts_state"
    enabled: bool
