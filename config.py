"""Centralized configuration: paths, model names, voice settings, study labels."""
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# Study session labels
#
# Which arm of the study this process is serving (architecture.txt). Both arms are THIS
# codebase — same model, same base prompt, same tools, same UI. The only difference is
# whether system_prompt.py injects the URL-derived profile summary:
#   arch1 — injection off. The generic baseline.
#   arch2 — injection on. The personalized architecture being evaluated.
#
# Read here rather than in backend/server.py because system_prompt.py needs it too, and
# two modules reading the same env var independently is how they drift apart. Set it when
# launching:  $env:JARVIS_STUDY_CONDITION = "arch1"
#
# Anything other than "arch1" leaves the profile injected, so the baseline has to be asked
# for explicitly — an unlabeled run is full Himavat (which is what the CLI and the eval
# harness want), never a silent baseline.
STUDY_CONDITION = os.environ.get("JARVIS_STUDY_CONDITION", "unspecified")

# Pseudonymous participant code (P01, P02, ...), matching reset_user_state.py's
# --participant labels. The only join key between a participant's arch1 and arch2 rows.
# Deliberately a code, not a name: the protocol keeps identity separate from task
# responses, so the code-to-person mapping lives outside this repo.
PARTICIPANT_ID = os.environ.get("JARVIS_PARTICIPANT_ID", "unassigned")


def profile_injection_enabled() -> bool:
    """Whether the cold-start profile is injected into the system prompt for this run.

    The single source of truth for the arch1/arch2 difference — system_prompt.py acts on
    it, and backend/server.py + inspect_prompt.py report on it, so what gets printed can't
    disagree with what the model actually receives.
    """
    return STUDY_CONDITION != "arch1"

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

# Spoken summary
#
# A long reply is displayed in full but SPOKEN as a summary (speech_summary.py). At
# SPEECH_RATE, 800 characters is already about a minute of audio the listener cannot skim
# or skip — past that, hearing the shape of the answer beats hearing all of it.
#
# The threshold is not much larger than a summary itself on purpose: replies just over it
# shorten only a little, which is harmless, while setting it high would leave exactly the
# three-minute answers this exists for unshortened. Same value for both arms — a
# per-arm threshold would make speech length a second difference between them.
SPOKEN_SUMMARY_MAX_CHARS = 800
SPOKEN_SUMMARY_SENTENCES = 5

# A sentence count alone doesn't bound anything — asked for five sentences, the model
# writes five 60-word ones and shortens a long answer by barely a fifth. The word budget
# is what actually makes it a summary. 100 words is roughly 35 seconds at SPEECH_RATE.
SPOKEN_SUMMARY_MAX_WORDS = 100

# Shorter than LLM_TIMEOUT_S because this call sits between the participant reading the
# answer and hearing it, with nothing happening in between. On timeout the full reply is
# spoken instead, so a low ceiling costs verbosity, never the turn.
#
# Not lower than this, though. speech_summary uses its own ChatGroq client, so its first
# call of a session pays for a fresh TLS handshake that the answer path has already made;
# at 10s that first summary timed out and the participant heard three and a half minutes
# of audio — the exact outcome this exists to avoid. Prefer waiting a few seconds over
# falling back.
SPOKEN_SUMMARY_TIMEOUT_S = 15

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
# Measured at 5 as well: no accuracy gain (6 of 10 correct either way) and the agent
# wandered into extra searches, so mean latency went 6.0s -> 7.9s. Left at 3.
MAX_TOOL_TURNS = 3

# Per-call timeout (seconds) for every ChatGroq client. Bounds a single HTTP
# call, not the whole agent loop — a multi-tool-turn request can still take
# multiples of this legitimately. Without it, a stalled connection (e.g. this
# machine's SSL cert flakiness) hangs the request forever and leaks a
# threadpool worker permanently.
LLM_TIMEOUT_S = 20