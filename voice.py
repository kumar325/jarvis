"""Voice I/O: recording, transcription, text-to-speech."""
import contextlib
import io
import re
import tempfile
from pathlib import Path

import sounddevice as sd
from scipy.io.wavfile import write
from scipy.io import wavfile
import whisper
import pyttsx3
import numpy as np
from config import (
    WHISPER_MODEL, VOICE_INDEX, SPEECH_RATE, RECORD_SECONDS, SAMPLE_RATE,
    WHISPER_LANGUAGE, WHISPER_PROMPT,
)

stt = whisper.load_model(WHISPER_MODEL)

# Above this, Whisper itself considers a segment to be non-speech.
NO_SPEECH_THRESHOLD = 0.6


def _normalize(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split()


_PROMPT_TOKENS = _normalize(WHISPER_PROMPT)


def _is_prompt_echo(text: str) -> bool:
    """Whisper regurgitates initial_prompt verbatim when handed silence or noise.

    Left unguarded that is worse than the mistranscription this prompt exists to fix: the
    fabricated sentence would be submitted as the participant's turn, answered by the LLM,
    and written to ratings.jsonl as something they never said.

    Matches only a contiguous run of the prompt (whole or truncated) covering most of it,
    so a participant genuinely naming their own campus is not discarded.
    """
    tokens = _normalize(text)
    if not tokens or len(tokens) < 0.6 * len(_PROMPT_TOKENS):
        return False
    joined, prompt_joined = " ".join(tokens), " ".join(_PROMPT_TOKENS)
    return joined in prompt_joined or prompt_joined in joined


def record(seconds=RECORD_SECONDS, fs=SAMPLE_RATE):
    print("Listening...", flush=True)
    audio = sd.rec(int(seconds * fs), samplerate=fs, channels=1)
    sd.wait()
    write("input.wav", fs, audio)
    return "input.wav"


def transcribe(path):
    sample_rate, audio = wavfile.read(path)
    if audio.dtype == np.int16:
        audio = audio.astype(np.float32) / 32768.0
    elif audio.dtype == np.int32:
        audio = audio.astype(np.float32) / 2147483648.0
    else:
        audio = audio.astype(np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    # Silence whisper's stderr chatter so it doesn't collide with terminal prompts
    with contextlib.redirect_stderr(io.StringIO()):
        result = stt.transcribe(
            audio,
            language=WHISPER_LANGUAGE,
            initial_prompt=WHISPER_PROMPT,
            # Each utterance is independent here — carrying decoded text between clips
            # lets one bad transcription drag the next one along with it.
            condition_on_previous_text=False,
        )

    segments = result.get("segments") or []
    # Whisper invents fluent text from silence — the pre-existing behaviour here was a
    # burst of unrelated multilingual prose. Either way, callers treat "" as "didn't hear
    # anything", which is the honest outcome; backend/server.py already surfaces it.
    if segments and all(s.get("no_speech_prob", 0.0) > NO_SPEECH_THRESHOLD for s in segments):
        return ""

    text = result["text"]
    if _is_prompt_echo(text):
        return ""
    return text


def speak(text):
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    engine.setProperty('voice', voices[VOICE_INDEX].id)
    engine.setProperty('rate', SPEECH_RATE)
    engine.setProperty('volume', 1.0)
    engine.say(text)
    engine.runAndWait()
    engine.stop()


def speak_to_bytes(text):
    """Same voice/rate as speak(), but rendered to a wav file and returned as bytes
    instead of played through the OS speakers — for the browser frontend's playback."""
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    engine.setProperty('voice', voices[VOICE_INDEX].id)
    engine.setProperty('rate', SPEECH_RATE)
    engine.setProperty('volume', 1.0)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    try:
        engine.save_to_file(text, path)
        engine.runAndWait()
        engine.stop()
        return Path(path).read_bytes()
    finally:
        Path(path).unlink(missing_ok=True)