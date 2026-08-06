"""Preference learning: rating storage, semantic retrieval of past examples."""
import json
import threading
from datetime import datetime

import numpy as np

from sentence_transformers import SentenceTransformer
from config import PREFS_FILE, EMBED_MODEL

print("Loading embedding model...")
try:
    # Prefer the cached local model to avoid SSL issues when Hugging Face is unreachable.
    embedder = SentenceTransformer(EMBED_MODEL, local_files_only=True)
except Exception:
    try:
        embedder = SentenceTransformer(EMBED_MODEL)
    except Exception:
        raise

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

# save_pref is a read-modify-write of the whole file. It is now called from the backend's
# threadpool (backend/server.py) as well as the jarvis.py CLI, and a second browser tab is
# a second writer — without this, concurrent ratings can lose pairs. Mirrors
# backend/ratings.py's _write_lock.
_write_lock = threading.Lock()

def save_pref(query, reply, rating):
    # Embedded before taking the lock — encoding is the slow part of this function, and
    # it depends on nothing that another writer could change.
    entry = {
        "query": query,
        "reply": reply,
        "rating": rating,
        "timestamp": datetime.now().isoformat(),
        "query_embedding": embed(query).tolist(),
    }
    with _write_lock:
        prefs = load_prefs()
        prefs.append(entry)
        PREFS_FILE.write_text(json.dumps(prefs, indent=2), encoding="utf-8")

def retrieve_examples(current_query, k=3):
    """Return (good_examples, bad_examples) most similar to current_query."""
    prefs = load_prefs()
    if not prefs:
        return [], []
    query_vec = embed(current_query)
    scored = []
    for p in prefs:
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