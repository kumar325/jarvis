#CODE

from dotenv import load_dotenv
load_dotenv()

import os
import sounddevice as sd
from scipy.io.wavfile import write
from scipy.io import wavfile
import whisper
import pyttsx3
import numpy as np
import json
import shutil
from pathlib import Path
from datetime import datetime
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from sentence_transformers import SentenceTransformer
from tavily import TavilyClient



# ---------- SANDBOX SETUP ----------
SANDBOX = Path("jarvis_sandbox").resolve()
SANDBOX.mkdir(exist_ok=True)

def safe_path(name):
    target = (SANDBOX / name).resolve()
    if not str(target).startswith(str(SANDBOX)):
        raise ValueError("Path escapes the sandbox — not allowed.")
    return target

# ---------- TOOLS ----------
@tool
def create_file(name: str, content: str = "") -> str:
    """Create a new text file in the sandbox with the given name and content."""
    if not name or not name.strip():
        return "Error: filename is required."
    path = safe_path(name)
    path.write_text(content, encoding="utf-8")
    return f"Created file '{name}'."

@tool
def read_file(name: str) -> str:
    """Read and return the contents of a file in the sandbox."""
    if not name or not name.strip():
        return "Error: filename is required."
    path = safe_path(name)
    if not path.exists():
        return f"File '{name}' does not exist."
    if not path.is_file():
        return f"'{name}' is not a readable file."
    return path.read_text(encoding="utf-8")

@tool
def move_file(name: str, new_name: str) -> str:
    """Move or rename a file within the sandbox. Use new_name as the destination filename."""
    if not name or not new_name:
        return "Error: both source and destination filenames are required."
    src = safe_path(name)
    dst = safe_path(new_name)
    if not src.exists():
        return f"File '{name}' does not exist."
    if not src.is_file():
        return f"'{name}' is not a movable file."
    shutil.move(str(src), str(dst))
    return f"Moved '{name}' to '{new_name}'."

@tool
def request_delete(name: str) -> str:
    """Request deletion of a file. This does NOT delete it — it asks the user to confirm first.
    Always call this before confirm_delete. After calling, tell the user what will be deleted
    and ask them to confirm out loud."""
    if not name or not name.strip():
        return "Error: filename is required."
    path = safe_path(name)
    if not path.exists():
        return f"File '{name}' does not exist, nothing to delete."
    if not path.is_file():
        return f"'{name}' is not a deletable file."
    return f"Ready to delete '{name}'. Ask the user to confirm before calling confirm_delete."

@tool
def confirm_delete(name: str) -> str:
    """Permanently delete a file. ONLY call this after the user has clearly said yes
    to a deletion you previously requested with request_delete."""
    if not name or not name.strip():
        return "Error: filename is required."
    path = safe_path(name)
    if not path.exists():
        return f"File '{name}' does not exist."
    if not path.is_file():
        return f"'{name}' is not a deletable file."
    path.unlink()
    return f"Deleted '{name}'."

@tool
def list_files() -> str:
    """List all files currently in the sandbox folder."""
    files = [f.name for f in SANDBOX.iterdir() if f.is_file()]
    return "Files: " + ", ".join(files) if files else "The sandbox is empty."



tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
@tool
def web_search(query: str) -> str:
    """Search the web for current information. Use this for news, current events,
    weather, sports scores, facts you're not sure about, or anything that might have
    changed recently. Returns a short summary of the top results."""
    try:
        result = tavily.search(
            query=query,
            max_results=3,
            search_depth="basic",
            include_answer=True,  # ask Tavily for a synthesized answer up top
        )
        out = ""
        if result.get("answer"):
            out += f"Quick answer: {result['answer']}\n\n"
        out += "Sources:\n"
        for r in result.get("results", []):
            out += f"- {r['title']}: {r['content'][:800]}\n"  # 800 not 300, no truncation marker
        return out
    except Exception as e:
        return f"Search failed: {e}"
    
@tool
def verify_search_result(question: str, retrieved_data: str) -> str:
    """Check if retrieved web data actually answers the user's question.
    Returns 'OK' if the data matches what was asked, or describes what's wrong."""
    check = llm_raw.invoke([
        SystemMessage(content="You are a fact-checker. Reply 'OK' if the retrieved data clearly answers the question. Otherwise describe the mismatch in one sentence."),
        HumanMessage(content=f"Question: {question}\n\nRetrieved data:\n{retrieved_data}")
    ])
    return check.content



TOOLS = [create_file, read_file, list_files, move_file, request_delete, confirm_delete, web_search, verify_search_result]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

# ---------- PREFERENCE LEARNING ----------
PREFS_FILE = Path("preferences.json")

# Load embedding model once at startup
# all-MiniLM-L6-v2 is small (~80MB), fast on CPU, and surprisingly strong for retrieval
print("Loading embedding model...")
embedder = SentenceTransformer("all-MiniLM-L6-v2")

def embed(text):
    """Convert text to a 384-dimensional vector."""
    return embedder.encode(text, convert_to_numpy=True)

def cosine_sim(a, b):
    """Cosine similarity between two vectors. Returns -1 to 1, higher = more similar."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def load_prefs():
    if PREFS_FILE.exists():
        return json.loads(PREFS_FILE.read_text(encoding="utf-8"))
    return []

def save_pref(query, reply, rating):
    prefs = load_prefs()
    prefs.append({
        "query": query,
        "reply": reply,
        "rating": rating,
        "timestamp": datetime.now().isoformat(),
        "query_embedding": embed(query).tolist(),  # cache the vector
    })
    PREFS_FILE.write_text(json.dumps(prefs, indent=2), encoding="utf-8")

def similarity(a, b):
    """Semantic similarity using sentence embeddings (replaces old keyword overlap)."""
    return cosine_sim(embed(a), embed(b))

def retrieve_examples(current_query, k=3):
    """Return (good_examples, bad_examples) most similar to current_query."""
    prefs = load_prefs()
    if not prefs:
        return [], []
    query_vec = embed(current_query)
    scored = []
    for p in prefs:
        # Use cached embedding if available, else compute on the fly
        if "query_embedding" in p:
            pref_vec = np.array(p["query_embedding"])
        else:
            pref_vec = embed(p["query"])
        sim = cosine_sim(query_vec, pref_vec)
        scored.append((sim, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    relevant = [p for sim, p in scored if sim > 0.5][:k * 2]
    good = [p for p in relevant if p["rating"] == "up"][:k]
    bad = [p for p in relevant if p["rating"] == "down"][:k]
    return good, bad

def build_system_message(current_query):
    """System prompt + retrieved good/bad examples for this query."""
    base = (
    "You are Jarvis, a helpful voice assistant. "
    "You can manage files in a sandbox and search the web using your tools. "
    "Keep spoken replies short, 1-2 sentences. "
    "WEB SEARCH: Use web_search whenever the user asks about current events, news, "
    "weather, sports scores, stock prices, recent releases, or anything that may have "
    "changed recently. Do not guess from memory — if you're not certain the information "
    "is current and accurate, search. Do NOT search for general knowledge, definitions, "
    "math, coding help, or things in our conversation history. "
    "QUERY SPECIFICITY: When using web_search, write specific queries with disambiguators. "
    "For a place, include state and country (e.g., 'Laguna Beach California USA weather' "
    "not 'Laguna Beach weather'). For people, include context (e.g., 'Tim Cook Apple CEO' "
    "not 'Tim Cook'). For events, include the year. Specific queries return correct results. "
    "GROUNDING: When the user disputes information you got from web_search, do not "
    "simply agree with them. Either re-search to verify, or stick with your sourced "
    "answer and tell them where it came from. Do not invent numbers to match the "
    "user's claim. "
    "AFTER you've gathered enough information from a tool to answer the user's question, "
    "STOP using tools and give the answer in plain text. Do NOT call additional tools "
    "unrelated to what the user asked. One tool call is usually enough — only chain "
    "tools if the user explicitly asks for multiple things in one request. "
    "FILE DELETION: To delete a file, first call request_delete, then tell the user "
    "exactly what will be deleted and ask them to confirm. Only call confirm_delete "
    "after the user clearly says yes. If they say no or seem unsure, do not delete."
)

    good, bad = retrieve_examples(current_query)
    if good or bad:
        base += "\n\nLEARNED USER PREFERENCES:"
    if good:
        base += "\n\nThe user rated these past responses HIGHLY — imitate their style:"
        for ex in good:
            base += f"\n  User asked: \"{ex['query']}\"\n  You said: \"{ex['reply']}\""
    if bad:
        base += "\n\nThe user rated these past responses POORLY — avoid this style:"
        for ex in bad:
            base += f"\n  User asked: \"{ex['query']}\"\n  You said: \"{ex['reply']}\""

    return SystemMessage(content=base)

# ---------- VOICE SETUP ----------
stt = whisper.load_model("small")
#llm = ChatGroq(model="openai/gpt-oss-120b").bind_tools(TOOLS)
#llm = ChatGroq(model="moonshotai/kimi-k2-instruct").bind_tools(TOOLS)
#llama-3.3-70b-versatile

llm = ChatGroq(model="openai/gpt-oss-120b").bind_tools(TOOLS)
llm_raw = ChatGroq(model="openai/gpt-oss-120b")

# Hard-pick voice index, 0 for male, 1 for female
VOICE_INDEX = 1

def record(seconds=10, fs=16000):
    print("Listening...")
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
    return stt.transcribe(audio)["text"]

def speak(text):
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    engine.setProperty('voice', voices[VOICE_INDEX].id)
    engine.setProperty('rate', 170)
    engine.setProperty('volume', 1.0)
    engine.say(text)
    engine.runAndWait()
    engine.stop()

# ---------- AGENT LOOP ----------
conversation = []  # no static SYSTEM anymore — built fresh each turn

def ask_jarvis(user_text):
    system_msg = build_system_message(user_text)
    messages = [system_msg] + [m for m in conversation if not isinstance(m, SystemMessage)]
    messages.append(HumanMessage(content=user_text))

    MAX_TOOL_TURNS = 3  # safety cap — prevents infinite tool-calling loops
    for turn in range(MAX_TOOL_TURNS):
        try:
            response = llm.invoke(messages)
        except Exception as e:
            err_msg = str(e)
            if "tool_use_failed" in err_msg or "Failed to" in err_msg:
                print(f"[model produced malformed tool call, falling back]")
                fallback = "I'm having trouble using my tools right now — try asking again."
                conversation.append(HumanMessage(content=user_text))
                conversation.append(SystemMessage(content=fallback))
                return fallback
            raise
        messages.append(response)
        if not response.tool_calls:
            conversation.append(HumanMessage(content=user_text))
            conversation.append(response)
            return response.content
        for call in response.tool_calls:
            tool_fn = TOOLS_BY_NAME.get(call["name"])
            if tool_fn is None:
                result = f"Unknown tool: {call['name']}"
            else:
                try:
                    result = tool_fn.invoke(call["args"])
                except Exception as e:
                    result = f"Tool error: {e}"
            print(f"[ran {call['name']} -> {result}]")
            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    # Hit the cap — force the LLM to answer with what it has
    print(f"[hit {MAX_TOOL_TURNS}-turn cap, forcing final answer]")
    messages.append(HumanMessage(content="Stop using tools and give me a final answer now based on what you've found."))
    response = llm.invoke(messages)
    conversation.append(HumanMessage(content=user_text))
    conversation.append(response)
    return response.content

# ---------- MAIN ----------
while True:
    input("Press Enter to talk...")
    path = record(10)
    user_text = transcribe(path)
    print(f"You: {user_text}")
    reply = ask_jarvis(user_text)
    print(f"Jarvis: {reply}")
    speak(reply)

    # Optional thumbs up/down feedback (Enter to skip)
    rating_input = input("Feedback (u=👍 / d=👎 / Enter to skip): ").strip().lower()
    if rating_input in ("u", "up", "1", "+"):
        save_pref(user_text, reply, "up")
        print("[saved 👍]")
    elif rating_input in ("d", "down", "0", "-"):
        save_pref(user_text, reply, "down")
        print("[saved 👎]")
    elif rating_input:
        print("[unrecognized, skipped]")

        