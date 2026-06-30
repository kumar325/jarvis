"""Jarvis — voice-controlled AI assistant with in-context RLHF."""
from voice import record, transcribe, speak
from agent_loop import ask_jarvis
from preferences import save_pref

while True:
    mode = input("Press Enter to talk, or type 't' for text input: ").strip().lower()

    if mode == "t":
        user_text = input("You (type): ").strip()
        if not user_text:
            print("[empty input, skipping]")
            continue
    else:
        path = record()
        user_text = transcribe(path)

    print(f"You: {user_text}")
    reply = ask_jarvis(user_text)
    print(f"Jarvis: {reply}")
    speak(reply)

    rating_input = input("Feedback (u=👍 / d=👎 / Enter to skip): ").strip().lower()
    if rating_input in ("u", "up", "1", "+"):
        save_pref(user_text, reply, "up")
        print("[saved 👍]")
    elif rating_input in ("d", "down", "0", "-"):
        save_pref(user_text, reply, "down")
        print("[saved 👎]")
    elif rating_input:
        print("[unrecognized, skipped]")