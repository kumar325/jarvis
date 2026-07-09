"""Typed schemas for the WebSocket message contract between the HUD frontend and this backend."""
from typing import Any, Literal
from pydantic import BaseModel


class UserTextMessage(BaseModel):
    """Client -> server: a text query to run through ask_jarvis()."""
    type: Literal["user_text"] = "user_text"
    text: str


class AssistantTextMessage(BaseModel):
    type: Literal["assistant_text"] = "assistant_text"
    text: str


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
