"""Preference learning: rating storage, semantic retrieval of past examples."""
import json
import os
import ssl
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np

# #region agent log
def _dbg_log(hypothesis_id, location, message, data):
    try:
        payload = {
            "sessionId": "f41442",
            "runId": "pre-fix",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open("debug-f41442.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _probe_ssl_and_network():
    paths = ssl.get_default_verify_paths()
    ssl_info = {
        "cafile": paths.cafile,
        "capath": paths.capath,
        "openssl_cafile": paths.openssl_cafile,
        "SSL_CERT_FILE": os.environ.get("SSL_CERT_FILE"),
        "REQUESTS_CA_BUNDLE": os.environ.get("REQUESTS_CA_BUNDLE"),
        "HF_HUB_CACHE": os.environ.get("HF_HUB_CACHE"),
    }
    _dbg_log("A", "preferences.py:_probe_ssl_and_network", "ssl_paths_and_env", ssl_info)

    try:
        import certifi
        certifi_path = certifi.where()
        ssl_info["certifi_path"] = certifi_path
        ssl_info["certifi_exists"] = Path(certifi_path).exists()
        _dbg_log("D", "preferences.py:_probe_ssl_and_network", "certifi_bundle", ssl_info)
    except Exception as e:
        _dbg_log("D", "preferences.py:_probe_ssl_and_network", "certifi_error", {"error": str(e)})

    hf_cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    model_cache_glob = list(hf_cache.glob("*MiniLM*")) if hf_cache.exists() else []
    _dbg_log(
        "C",
        "preferences.py:_probe_ssl_and_network",
        "hf_cache_state",
        {
            "hf_cache_exists": hf_cache.exists(),
            "minilm_cache_dirs": [p.name for p in model_cache_glob[:5]],
            "minilm_cache_count": len(model_cache_glob),
        },
    )

    urllib_ok = False
    urllib_err = None
    try:
        urllib.request.urlopen("https://huggingface.co", timeout=10)
        urllib_ok = True
    except Exception as e:
        urllib_err = str(e)
    _dbg_log(
        "B",
        "preferences.py:_probe_ssl_and_network",
        "urllib_https_test",
        {"ok": urllib_ok, "error": urllib_err},
    )

    httpx_ok = False
    httpx_err = None
    try:
        import httpx
        httpx.get("https://huggingface.co", timeout=10)
        httpx_ok = True
    except Exception as e:
        httpx_err = str(e)
    _dbg_log(
        "B",
        "preferences.py:_probe_ssl_and_network",
        "httpx_https_test",
        {"ok": httpx_ok, "error": httpx_err},
    )


_probe_ssl_and_network()
# #endregion

from sentence_transformers import SentenceTransformer
from config import PREFS_FILE, EMBED_MODEL

print("Loading embedding model...")
try:
    embedder = SentenceTransformer(EMBED_MODEL)
    # #region agent log
    _dbg_log("E", "preferences.py:embedder_load", "model_load_ok", {"model": EMBED_MODEL})
    # #endregion
except Exception as e:
    # #region agent log
    _dbg_log(
        "E",
        "preferences.py:embedder_load",
        "model_load_failed",
        {"model": EMBED_MODEL, "error_type": type(e).__name__, "error": str(e)},
    )
    # #endregion
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