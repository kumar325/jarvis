"""Voice I/O: recording, transcription, text-to-speech."""
import contextlib
import io
import tempfile
from pathlib import Path

import sounddevice as sd
from scipy.io.wavfile import write
from scipy.io import wavfile
import whisper
import pyttsx3
import numpy as np
from config import WHISPER_MODEL, VOICE_INDEX, SPEECH_RATE, RECORD_SECONDS, SAMPLE_RATE

stt = whisper.load_model(WHISPER_MODEL)


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
        result = stt.transcribe(audio)
    return result["text"]


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