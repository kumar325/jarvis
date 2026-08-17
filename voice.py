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


def _heading_or_bullet_to_sentence(line: str) -> str:
    """Strip a leading markdown marker and make what's left end like a sentence.

    Removing the marker alone is not enough: "Breakfast" and "Eggs and toast" as bare
    lines run together into "Breakfast Eggs and toast" with no pause, because the engine
    breaks on punctuation, not on newlines.
    """
    stripped = re.sub(r"^\s*(?:>+\s*)?(?:#{1,6}\s*|[-*+•]\s+|\d{1,2}[.)]\s+)", "", line)
    stripped = re.sub(r"\s*#*\s*$", "", stripped).strip()
    if stripped and stripped[-1] not in ".!?,:;":
        stripped += "."
    return stripped


def _money(match: re.Match) -> str:
    amount, magnitude = match.group(1), match.group(2)
    return f"{amount} {magnitude} dollars" if magnitude else f"{amount} dollars"


def normalize_for_speech(text: str) -> str:
    """Rewrite a reply into something the speech engine says correctly.

    SAPI5 reads symbols literally ("&" as "ampersand"), spells hyphen-joined numbers out
    digit by digit or reads the hyphen as "minus", and reads stray markdown punctuation
    aloud. The system prompt asks the model to avoid all of that, but a prompt is a
    request — this is the guarantee. Both layers earn their place: the prompt keeps the
    *displayed* transcript clean, this keeps the *audio* clean when the model ignores it.

    AUDIO ONLY. Called inside speak()/speak_to_bytes() and nowhere else, so the string
    the UI renders, register_exchange() stores and ratings.jsonl logs is untouched — the
    participant still rates the answer they can read. It is also deterministic, arm-blind
    and offline: no LLM call, no condition, no profile, so it cannot become a second
    personalization channel and cannot cost a turn.

    Never raises. On any regex or unicode surprise it returns the input unchanged, which
    is exactly the old behavior.
    """
    try:
        s = text or ""

        # Links and addresses first, before symbol substitution — otherwise a "&" or "%"
        # inside a query string would be spoken as a word.
        s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)              # [text](url) -> text
        s = re.sub(r"https?://(?:www\.)?([^\s/)>\]]+)\S*", r"\1", s)  # url -> bare domain
        s = re.sub(r"\bwww\.([^\s/)>\]]+)\S*", r"\1", s)
        s = re.sub(r"([\w.+-]+)@([\w.-]+\.\w+)", r"\1 at \2", s)

        # Markdown structure.
        s = re.sub(r"```[\s\S]*?```", " ", s)                        # fenced code blocks
        s = s.replace("`", "")
        lines = []
        for line in s.splitlines():
            if re.fullmatch(r"\s*\|?[\s:|+-]{3,}\|?\s*", line):      # table rule row
                continue
            # Strip the outer pipes before the inner ones become commas, or every table
            # row is spoken starting with a stray "comma".
            line = re.sub(r"^\s*\|\s*|\s*\|\s*$", "", line)
            lines.append(_heading_or_bullet_to_sentence(line.replace("|", ", ")))
        s = "\n".join(lines)
        s = s.replace("*", "")
        s = s.replace("_", " ")                                      # snake_case -> words

        # Numbers. Ranges and scores before anything else touches the hyphen.
        s = re.sub(r"(\d)\s*[-–—]\s*(?=\d)", r"\1 to ", s)
        s = re.sub(r"#\s*(?=\d)", "number ", s)
        s = re.sub(r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|trillion)?",
                   _money, s, flags=re.IGNORECASE)

        # Symbols.
        s = s.replace("%", " percent")
        s = re.sub(r"°\s*F\b", " degrees Fahrenheit", s)
        s = re.sub(r"°\s*C\b", " degrees Celsius", s)
        s = s.replace("°", " degrees")
        s = s.replace("&", " and ")
        s = s.replace("+", " plus ")
        s = s.replace("=", " equals ")
        # "about ~20" would otherwise become "about about 20".
        s = re.sub(r"\b(about|around|approximately)\s+~\s*(?=\d)", r"\1 ", s, flags=re.IGNORECASE)
        s = re.sub(r"~\s*(?=\d)", "about ", s)
        s = re.sub(r"\band\s*/\s*or\b", "and or", s, flags=re.IGNORECASE)  # not "and or or"
        s = re.sub(r"(?<=[A-Za-z])\s*/\s*(?=[A-Za-z])", " or ", s)   # he/she, on/off
        s = s.replace("$", " dollars")                               # any stray $ left

        # Abbreviations the engine spells out letter by letter.
        s = re.sub(r"\be\.g\.,?", "for example", s, flags=re.IGNORECASE)
        s = re.sub(r"\bi\.e\.,?", "that is", s, flags=re.IGNORECASE)
        s = re.sub(r"\bvs\.?(?=\s|$)", "versus", s, flags=re.IGNORECASE)
        s = re.sub(r"\betc\.", "et cetera", s, flags=re.IGNORECASE)
        s = re.sub(r"\bapprox\.", "approximately", s, flags=re.IGNORECASE)
        s = re.sub(r"\bw/(?=\s)", "with", s, flags=re.IGNORECASE)

        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s).strip()
        # An empty result means a substitution ate the whole reply; speak the original.
        return s or (text or "")
    except Exception as e:
        print(f"[voice] speech normalization failed, speaking raw text: {e}", flush=True)
        return text or ""


def speak(text):
    text = normalize_for_speech(text)
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
    text = normalize_for_speech(text)
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