"""Centralized configuration: paths, model names, voice settings."""
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# Paths
#
# Anchored to the project root (this file's directory), never to the process CWD.
# These are resolved by three separate entrypoints — jarvis.py, backend/server.py under
# uvicorn, and eval/run_eval.py — and a bare relative Path would silently point each one
# at a different file if it were launched from anywhere but the root. That failure is
# invisible: a second set of state files accumulates, and reset_user_state.py (which
# anchors to its own directory) neither archives nor wipes them, so the next participant
# inherits the previous one's state. Keep in sync with reset_user_state.py's STATE_FILES.
PROJECT_ROOT = Path(__file__).resolve().parent
SANDBOX = PROJECT_ROOT / "jarvis_sandbox"
SANDBOX.mkdir(exist_ok=True)
PREFS_FILE = PROJECT_ROOT / "preferences.json"

# Models
LLM_MODEL = "openai/gpt-oss-120b"
WHISPER_MODEL = "small"
EMBED_MODEL = "all-MiniLM-L6-v2"

# Voice
VOICE_INDEX = 1  # 0 = male, 1 = female
SPEECH_RATE = 170
RECORD_SECONDS = 10
SAMPLE_RATE = 16000

# Whisper decoding
#
# Pinning the language skips per-clip auto-detection, which is unreliable on the short,
# noisy utterances this app records and can silently degrade the whole transcript.
WHISPER_LANGUAGE = "en"

# Primes Whisper's decoder with context so local proper nouns resolve instead of being
# guessed at phonetically — "Bothell" was coming back as "Balthol" and "Buffalo", and the
# LLM then answered confidently about Baltimore.
#
# Deliberately a fluent sentence rather than a comma-separated keyword list: Whisper can
# echo prompt tokens into the transcript, and it is far likelier to splice in stray words
# from a word-salad prompt than from natural prose. Keep it short and keep it grammatical.
# Edit this per deployment — it should name the places and institutions your participants
# will actually say.
WHISPER_PROMPT = (
    "The speaker is a student at the University of Washington Bothell, "
    "near Seattle, Kirkland, and Redmond in Washington state."
)

# Agent
MAX_TOOL_TURNS = 3

# Per-call timeout (seconds) for every ChatGroq client. Bounds a single HTTP
# call, not the whole agent loop — a multi-tool-turn request can still take
# multiples of this legitimately. Without it, a stalled connection (e.g. this
# machine's SSL cert flakiness) hangs the request forever and leaks a
# threadpool worker permanently.
LLM_TIMEOUT_S = 20