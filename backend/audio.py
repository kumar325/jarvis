"""Bridges browser audio bytes <-> voice.transcribe()/voice.speak_to_bytes(), reusing the
existing Whisper model and pyttsx3 voice settings from voice.py/config.py unchanged."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice import transcribe, speak_to_bytes


def transcribe_bytes(wav_bytes: bytes) -> str:
    """Write the browser-recorded wav to a temp file and run it through the same
    transcribe() the CLI path uses — the frontend pre-encodes to 16kHz mono wav."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav_bytes)
        path = f.name
    try:
        return transcribe(path)
    finally:
        Path(path).unlink(missing_ok=True)


def synthesize(text: str) -> bytes:
    return speak_to_bytes(text)
