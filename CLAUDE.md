# Jarvis — Claude Code Context

## Project overview
Jarvis is a modular Python voice assistant with in-context RLHF and multi-layer
personalization. Built as a UW Bothell CS capstone (Summer 2026) targeting a
NeurIPS or ACL workshop paper. Faculty advisor: Dr. Champion.

**Paper claim (working):**
"In-context preference learning produces measurable behavior change with N user
ratings, and we characterize where it works and where weight-based RLHF would
do better."

**Repo:** private at kumar325/jarvis
**Local path:** C:\Users\Mahar\OneDrive\Desktop\KaranC++\jarvis\
**Python:** 3.12 at C:\Users\Mahar\AppData\Local\Programs\Python\Python312\
**Venv:** .venv — activate with .venv\Scripts\Activate.ps1

---

## Tech stack
- **STT:** Whisper small
- **TTS:** pyttsx3 (voice index 1, rate 170)
- **LLM:** Groq via LangChain (current model: openai/gpt-oss-120b)
- **Web search:** Tavily (advanced depth, max_results=5, content slice 1500 chars)
- **Embeddings:** sentence-transformers all-MiniLM-L6-v2
- **URL scraping:** requests + BeautifulSoup
- **Eval:** UpTrain with groq/llama-3.3-70b-versatile as judge LLM
- **SSL fix:** truststore.inject_into_ssl() at startup (corporate cert issue on this machine)

---

## File architecture
```
jarvis.py           — thin main loop, Enter-to-talk or t-for-text input
config.py           — constants and env loading
voice.py            — Whisper STT + pyttsx3 TTS
agent_loop.py       — LangChain agent, MAX_TOOL_TURNS=3, graceful fallback
system_prompt.py    — builds dynamic system prompt (base + profile + facts + style + prefs)
preferences.py      — in-context RLHF: stores preference pairs, cosine-similarity retrieval
user_profile.py     — URL cold-start scraping + remember/forget facts
style_tracker.py    — 20-utterance rolling buffer, style summary every 5 turns
tools/
  web.py            — Tavily search + verify_search_result (llm_raw cross-source check)
  files.py          — sandboxed file tools with two-step delete confirmation
  __init__.py
eval/
  run_eval.py       — ablation harness, writes CSV to eval/results/
  ablations.py      — capture_tool_trace, apply_ablation, snapshot_system_state
  test_queries.json — test queries (currently being overhauled — see below)
```

**Gitignored:** .env, preferences.json, user_profile.json, user_style.json, jarvis_sandbox/

---

## Personalization layers (injection order in system prompt)
1. Base instructions (personality, tools, grounding, uncertainty calibration)
2. URL-derived profile summary (from user_profile.json)
3. Remembered facts list (from user_profile.json → remembered_facts)
4. Style summary (from user_style.json)
5. Preference examples — good then bad (retrieved via cosine similarity from preferences.json)

---

## Data files — handle with care
- **user_profile.json** — real user profile, do NOT write directly. Use remember_fact()
  only. Dedup is currently exact-string match (known issue — needs fuzzy matching).
- **preferences.json** — preference pairs with cached embeddings. Don't overwrite.
- **user_style.json** — style summary. Safe to reset for testing.

---

## Eval harness — current state and known issues

### What works
- 5 ablation configs: full, no_memory, no_style, no_prefs, no_web_search
- 4 UpTrain metrics per query: context_relevance, response_relevance,
  response_completeness, factual_accuracy
- CSV output to eval/results/eval_scores_<timestamp>.csv

### Active overhaul in progress
The eval was showing no_memory scoring HIGHER than full (1.0 vs 0.611 on
response_relevance) because queries were profile-independent (weather, sports).
The following changes are being implemented:

1. **Replace test_queries.json** with 20+ queries split into categories:
   - Profile-dependent (correct answer requires knowing user is vegetarian,
     works night shifts) — e.g. "what should I make for dinner tonight?"
   - Memory-recall (explicitly test remembered facts retrieval)
   - Style-dependent (measure tone change from style mirroring)
   - Web-dependent (current weather/sports — keep a few)

2. **Add ground_truth_expectation field** per query for profile-dependent ones
   (e.g. "response should mention vegetarian options") and score against it as
   a 5th UpTrain metric

3. **Add personalization_used boolean** — did the signal actually appear in
   retrieved context, not just get loaded?

4. **Add delta_score column** — (full_score - ablated_score) per query per metric.
   This is the number the paper needs.

5. **Fix state isolation** — copy user_profile.json to temp before eval run,
   restore after. Currently q3 ("Remember I'm vegetarian...") pollutes the real
   profile on every run.

---

## Known bugs / tech debt
- user_profile.json dedup is exact-string match only → near-duplicates accumulate
  across eval runs (e.g. "The user is vegetarian." and "The user is vegetarian"
  as separate entries). Needs cosine similarity dedup using the existing embedder.
- SSL cert issue on this machine fixed via truststore — don't remove that call.
- HF_HUB_OFFLINE=1 can be set if Hugging Face SSL check fails at startup
  (model is already cached locally).
- Tavily advanced search costs 2x credits vs basic.

---

## Agent behavior
- MAX_TOOL_TURNS=3 with forced final-answer message at cap
- Empty response → returns honest "couldn't find a clear answer" message
- Malformed tool calls → graceful fallback, doesn't crash
- Tool trace printed as dimmed ANSI "Jarvis (thinking):" with 120-char truncation
- verify_search_result uses a separate llm_raw (no tools) for cross-source contradiction detection

---

## Running the project
```powershell
# Activate venv
.venv\Scripts\Activate.ps1

# Run Jarvis
python jarvis.py

# Run eval (full)
python eval/run_eval.py

# Run eval (cheap subset)
python eval/run_eval.py --ablations no_web_search,full --limit 3
```

---

## Paper todos (from Dr. Champion)
- [x] Investigate UpTrain for automatic evaluation
- [x] Functionalize/reorganize files
- [x] Improve RAG pipeline grounding
- [ ] Fix eval to test personalization-dependent queries (in progress)
- [ ] Tune hyperparameters (k, similarity threshold for preference retrieval)
- [ ] Plan user study with 5-10 live test subjects
- [ ] Investigate FAISS/ChromaDB for faster preference retrieval (future work)
- [ ] Active learning layer — Jarvis proactively asks profile-filling questions
- [ ] Investigate MCP

---

## What NOT to do
- Do not modify user_profile.json directly — use remember_fact() / forget_fact()
- Do not change the system prompt injection order without checking all 5 layers
- Do not remove truststore.inject_into_ssl() — will break on this machine
- Do not run full eval (30 queries) without checking Tavily credit balance first
