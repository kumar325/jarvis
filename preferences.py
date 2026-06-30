"""Preference learning: rating storage, semantic retrieval of past examples."""
import json
import numpy as np
from datetime import datetime
from sentence_transformers import SentenceTransformer
from config import PREFS_FILE, EMBED_MODEL

print("Loading embedding model...")
embedder = SentenceTransformer(EMBED_MODEL)

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
        "query_embedding": embed(query).tolist(),
    })
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