"""Jarvis — voice-controlled AI assistant with in-context RLHF."""
import os
import warnings

# Suppress noisy startup warnings before any imports
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["PYTHONWARNINGS"] = "ignore"
warnings.filterwarnings("ignore")

# Use Windows certificate store so httpx (Groq, Hugging Face) can verify TLS.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from voice import record, transcribe, speak
from agent_loop import ask_jarvis
from preferences import save_pref
from speech_summary import summarize_for_speech
from style_tracker import record_utterance

while True:
    mode = input("[Enter=voice, t=text] ").strip().lower()

    if mode == "t":
        user_text = input(">>> ").strip()
        if not user_text:
            print("[empty input, skipping]", flush=True)
            continue
    else:
        path = record()
        user_text = transcribe(path)

    print(f"You: {user_text.strip()}", flush=True)
    record_utterance(user_text)
    reply = ask_jarvis(user_text)
    print(f"Jarvis: {reply}", flush=True)
    # Printed in full, spoken as a summary when it's long — same rule the web path uses,
    # called from both so the two can't drift. The rating below is on `reply`, the answer
    # that was printed, not on the shortened audio.
    spoken = summarize_for_speech(reply)
    if spoken != reply:
        print(f"[speaking a {len(spoken)}-char summary]", flush=True)
    speak(spoken)

    rating_input = input("Feedback (u=👍 / d=👎 / Enter to skip): ").strip().lower()
    if rating_input in ("u", "up", "1", "+"):
        save_pref(user_text, reply, "up")
        print("[saved 👍]", flush=True)
    elif rating_input in ("d", "down", "0", "-"):
        save_pref(user_text, reply, "down")
        print("[saved 👎]", flush=True)
    elif rating_input:
        print("[unrecognized, skipped]", flush=True)
