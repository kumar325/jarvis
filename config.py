"""Centralized configuration: paths, model names, voice settings."""
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

# Paths
SANDBOX = Path("jarvis_sandbox").resolve()
SANDBOX.mkdir(exist_ok=True)
PREFS_FILE = Path("preferences.json")

# Models
LLM_MODEL = "openai/gpt-oss-120b"
WHISPER_MODEL = "small"
EMBED_MODEL = "all-MiniLM-L6-v2"

# Voice
VOICE_INDEX = 1  # 0 = male, 1 = female
SPEECH_RATE = 170
RECORD_SECONDS = 10
SAMPLE_RATE = 16000

# Agent
MAX_TOOL_TURNS = 3