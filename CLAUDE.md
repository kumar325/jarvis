# Jarvis — Claude Code Context

## Project overview
Jarvis is a modular Python voice assistant with in-context RLHF and multi-layer
personalization. Built as a research project, targeting a high tier ML conference.

**Paper claim (working):**
"In-context preference learning produces measurable behavior change with N user
ratings, and we characterize where it works and where weight-based RLHF would
do better."

**Repo:** private (see `git remote -v`)
**Local path:** the repo root — this file's directory
**Python:** 3.14.6 at %LOCALAPPDATA%\Python\pythoncore-3.14-64\
**Venv:** .venv — activate with .venv\Scripts\Activate.ps1

`python` on PATH resolves to the Windows Store stub, **not** the venv — running
`python jarvis.py` without activating first fails with ModuleNotFoundError on
sounddevice (and every other dependency). Activate, or call
`.venv\Scripts\python.exe` directly.

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
system_prompt.py    — builds system prompt (base + URL profile only; see layers below)
preferences.py      — in-context RLHF: stores preference pairs, cosine-similarity retrieval
user_profile.py     — URL cold-start scraping + remember/forget facts
style_tracker.py    — 20-utterance rolling buffer, style summary every 5 turns
reset_user_state.py — wipe/archive participant state between sessions (stdlib only)
inspect_prompt.py   — dump the assembled system prompt for debugging
tools/
  web.py            — Tavily search + verify_search_result (llm_raw cross-source check)
  files.py          — sandboxed file tools with two-step delete confirmation
  __init__.py       — TOOLS list; remember/forget/learn_about_user NOT bound (see layers)
backend/            — FastAPI WebSocket server wrapping ask_jarvis() for the web UI
  server.py         — /ws endpoint, TTS state, rating + set_tts control messages
  audio.py          — browser wav bytes <-> voice.transcribe() / speak_to_bytes()
  ratings.py        — appends thumbs up/down rows to study_data/ratings.jsonl
  surveys.py        — appends post-task survey rows to study_data/survey_responses.csv,
                      derives the task number and arm position from that file
summarize_session.py — read a session back: exchanges/task, durations, ratings, surveys
  state.py          — /vitals /directives /documents REST payloads (no longer rendered)
  ws_messages.py    — pydantic schemas for the client/server message contract
frontend/           — Vite + React + Tailwind study UI (see frontend/src/)
  src/App.tsx       — wiring: socket, audio capture, input mode, rating gate, survey gate
  src/hooks/        — useJarvisSocket, useAudioCapture, useAudioPlayback, useOrbAmplitude
  src/components/   — layout/ (Header, Clock, MuteButton, FinishTaskButton, Shell),
                      center/ (Orb, Conversation, CommandInput, RatingPrompt, TaskSurvey,
                      ArchCompleteNotice)
eval/
  run_eval.py       — ablation harness, writes CSV to eval/results/
  ablations.py      — capture_tool_trace, apply_ablation, snapshot_system_state
  test_queries.json — test queries, split into profile/memory/style/web/general categories
```

**Gitignored:** .env (root and frontend/), preferences.json, user_profile.json,
user_style.json, jarvis_sandbox/, study_data/, input.wav, .venv/, .cursor/, .claude/

`frontend/.env` is gitignored but only holds `VITE_WS_URL` — no secret. A fresh clone
has no copy of it and falls back to the default in useJarvisSocket.ts, so keep that
default and the backend's port in sync (both 8000).

---

## Personalization layers (injection order in system prompt)

**This repo is BOTH arms** (see architecture.txt). They are the same code — same model,
same base prompt, same tools, same UI, same survey, same log files. The only difference is
whether `system_prompt.py` injects the URL-derived profile summary:

- `JARVIS_STUDY_CONDITION=arch2` → injected. The personalized architecture.
- `JARVIS_STUDY_CONDITION=arch1` → not injected. The generic baseline.
- anything else (CLI, eval harness) → injected. The baseline must be asked for explicitly.

`config.profile_injection_enabled()` is the single source of that decision;
`system_prompt.py` acts on it, `backend/server.py` and `inspect_prompt.py` report on it, so
what gets printed can't disagree with what the model receives.

One repo rather than two on purpose: "personalization is the only variable" then holds by
construction. With two repos it would depend on keeping the survey, the CSV schema, the
WebSocket contract and the UI byte-identical by hand — and a drifted *instrument* is a
worse confound than a drifted treatment, because it's invisible.

The profile is seeded **once per participant**, not per arm, and both arms run against that
same on-disk state. So under arch1 there is usually a perfectly good summary sitting in
user_profile.json that must not be injected — which is why the gate is on the arm, never on
whether the file happens to be populated.

1. Base instructions (personality, tools, grounding, uncertainty calibration)
2. URL-derived profile summary (from user_profile.json) — **the only personalization layer**

Three layers were removed so a study result can be attributed to the cold-start profile
alone, rather than to whichever mechanism happened to fire:

- **Remembered facts** — removed, along with `remember`/`forget` from `tools/__init__.py`.
  The model calling `remember` mid-session was a second personalization channel that
  accumulated during the three tasks. `learn_about_user` was unbound for the same reason
  and is the most damaging of the three: it wraps `learn_from_url`, which *overwrites*
  `profile["summary"]`, so one mid-session link would discard the seeded cold start
  entirely. Seeding happens once per participant, in reset_user_state.py, before the
  session.
- **Style summary** — removed from the prompt. Still *collected*: `backend/server.py`
  calls `record_utterance` on every web turn.
- **Preference examples** — removed from the prompt. Still *collected*:
  `backend/server.py` calls `save_pref` on every thumbs up/down.

The modules themselves (user_profile.remember_fact, style_tracker, preferences) still
exist and still work — they're used by the jarvis.py CLI and the eval harness. They are
simply no longer injected into the prompt.

### Collected but not injected

`user_style.json` and `preferences.json` are written on the web path but never read back
into the system prompt. Keep those two facts separate — they are not in tension:

- **Write path** — the browser session now produces the same on-disk state a CLI session
  does, so the eval harness and post-hoc analysis have something to work with. Before this
  the web UI collected none of it.
- **Read path** — `system_prompt.py` still injects base instructions + URL profile only.
  Re-injecting either file would be a second personalization channel and would make an
  Arch 2 result impossible to attribute to the cold-start profile alone.

Ratings go to **both** `study_data/ratings.jsonl` and `preferences.json`. ratings.jsonl is
the study's source of truth — it is the only one carrying `participant_id` and
`condition`. preferences.json is a flat list with neither, so it is per-session scratch:
it is only meaningful if `reset_user_state.py --participant P0X` runs between every
participant, which archives it to `study_data/P0X/`.

`backend/state.py` also *reads* all three files, but only to build the `/vitals` HUD
counters — that is not prompt injection, and PREFERENCE EXAMPLES climbing during a session
is the cheapest end-to-end check that collection is working.

Mute/unmute phrases ("talk off", "mute") are recorded by the CLI but deliberately NOT by
the web path — `record_utterance` sits after the `parse_tts_command` guard, since a
control phrase is not a speech sample worth mirroring.

### Post-task survey (study_data/survey_responses.csv)

Separate from the per-response thumbs up/down, which is unchanged and still fires on every
model reply. The survey is one row per *task*: the moderator clicks **Finish Task** in the
header, the orb and input are replaced by a three-question card (personalized 1-5,
accurate yes/partially/no, trust 1-5), and all three are mandatory before Submit unlocks —
the same disable-until-answered contract as the rating prompt.

Columns: `participant_id, arch, task_number, personalized_rating, accuracy_rating,
trust_rating, timestamp, session_id, arch_position`. Append new columns at the end;
analysis and Excel both depend on the order. `arch` carries the same `arch1`/`arch2` string as ratings.jsonl's
`condition` — the column is named `arch` per the survey spec, the values match the rest of
the repo.

Two design points worth not undoing:

- **The server assigns `task_number`**, by counting existing rows for this
  (participant, arch) — the client never sends it. A browser refresh resets all frontend
  state, so a client-owned counter would restart at 1 and log two rows as task 1.
  `reset_user_state.py` never touches this file (it only clears the three personalization
  JSONs and archives *into* study_data/), so the count survives resets and restarts.
- **Submission is server-confirmed, not optimistic.** A rating clears its gate on click so
  a disk error can't strand a participant mid-conversation; a survey keeps the filled-in
  card up until `survey_recorded` arrives. There are only three of these per arm and the
  moderator is already at the screen, so a retry beats a silent drop. Failures come back as
  `survey_error` (not `ErrorMessage`) specifically so they never render into the
  participant's transcript.

After task 3, the UI shows "Arch complete — ready for next phase" instead of returning to
the input box. It's dismissable — a 4th task still logs honestly as task 4 rather than
being blocked.

---

## Data files — handle with care
- **user_profile.json** — real user profile, do NOT write directly. Use remember_fact()
  only. Dedup is currently exact-string match (known issue — needs fuzzy matching).
- **preferences.json** — preference pairs with cached embeddings. Don't overwrite.
- **user_style.json** — style summary. Safe to reset for testing.

---

## Eval harness — current state and known issues

### What works
- 3 ablation configs: full, no_memory (= no profile), no_web_search. no_style and
  no_prefs were dropped when those layers left the prompt — there was nothing left for
  them to ablate, and patching functions system_prompt no longer imports raises
  AttributeError. Restore them alongside the injection blocks if a layer comes back.
- test_queries.json has 22 queries split into categories — profile (7),
  memory (5), style (4), web (4), general (2) — so personalization-dependent
  queries actually have a personalization-dependent correct answer (the old
  set was profile-independent, which is why no_memory used to outscore full)
- 5 UpTrain metrics per query: context_relevance, response_relevance,
  response_completeness, factual_accuracy, plus ground_truth_adherence
  (scored via GuidelineAdherence against each query's ground_truth_expectation,
  for profile/memory/style queries)
- personalization_used boolean — whether a loaded signal (fact/profile/style/
  example) actually left a keyword/phrase trace in the response, not just
  whether it was available (see check_personalization_used in ablations.py)
- delta_<metric> columns (full_score - ablated_score) per query — the number
  that quantifies each feature's contribution
- State isolation: preserve_file() snapshots user_profile.json before the run
  and restores it after (kept even though the agent can no longer call remember —
  the CLI path and future ablations still can)
- CSV output to eval/results/eval_scores_<timestamp>.csv

Last full run (all 22 queries x 5 ablations): eval/results/eval_scores_20260707_002245.csv.
no_memory drops ground_truth_adherence 0.812 -> 0.438 and no_web_search zeroes
out context_relevance (0.182 -> 0.0), confirming the harness now detects each
feature's contribution as expected.

**That run predates the Arch 2 strip and is no longer comparable.** It was scored against
a prompt carrying all five layers; the current prompt carries one. The memory (5) and
style (4) query categories in test_queries.json now have no mechanism to answer them —
the agent can't call remember, and style is never injected — so those 9 queries will
score badly by construction rather than by regression. Re-baseline before reading any
delta, and expect the query set itself to need revisiting.

---

## Known bugs / tech debt
- user_profile.json dedup is exact-string match only → near-duplicates accumulate
  across eval runs (e.g. "The user is vegetarian." and "The user is vegetarian"
  as separate entries). Needs cosine similarity dedup using the existing embedder.
  Lower priority now that the agent can't call remember on the web path — only the
  jarvis.py CLI and the eval harness still write facts.
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

### Running a study session (web UI)
```powershell
# 1. ONCE per participant — reset state and seed the cold-start profile. Seed it even
#    when arch1 runs first: it's per-participant, and arch1 simply never reads it.
python reset_user_state.py --participant P03 --profile-url https://... -y

# 2. Backend — label the session BEFORE starting it. Both vars are read once at import,
#    so restart the backend between arms AND between participants.
$env:JARVIS_STUDY_CONDITION = "arch1"   # arch1 | arch2 — see label conventions below
$env:JARVIS_PARTICIPANT_ID  = "P03"     # P01, P02, ... zero-padded
.venv\Scripts\python.exe -m uvicorn backend.server:app --port 8000

# 3. BETWEEN ARMS (same participant): no reset, no re-scrape. Restart the backend with
#    the other condition and reload the browser tab (which clears the conversation).
$env:JARVIS_STUDY_CONDITION = "arch2"
.venv\Scripts\python.exe -m uvicorn backend.server:app --port 8000

# Frontend (separate terminal)
cd frontend; npm run dev
```
The backend prints `[jarvis] study condition=… participant=…` at startup — check it
before the participant sits down. Unset values fall back to `unspecified` /
`unassigned` rather than guessing, so an unlabeled session is obvious in the log.

It also prints one line per post-task survey (`task survey recorded: participant=… arch=…
task=…`). Since the task number is derived from survey_responses.csv, that line is the
cheapest check that the label vars are right — a survey landing as task 1 when you expected
task 3 means the participant or arch string doesn't match the earlier rows.

### Cold-start profile (arch2 only)

The URL-derived summary is Arch 2's **only** personalization layer. With it empty, the
backend still answers normally and still stamps `arch2` on every rating and survey row — so
the session looks fine, produces data, and is actually running the arch1 baseline. Nothing
downstream can detect that afterwards. Two mechanisms exist so that state can't be reached
by accident:

1. **`reset_user_state.py --profile-url <URL>`** seeds it as the last step of the reset,
   after the wipe (which blanks user_profile.json) and after the archive. One command per
   participant rather than two, because a separate seeding step is one that gets skipped.
   If the fetch or the Groq call fails it exits **2** with a loud banner — at that point
   state is already wiped, so a silent failure is exactly the dangerous case.
2. **The backend refuses to start** when `JARVIS_STUDY_CONDITION=arch2` and the profile is
   empty. It checks `get_profile_summary()` — the same function system_prompt.py injects
   from, so the check can't drift from what the model actually sees. Scoped to an
   explicitly-labeled arch2 process: an unlabeled dev run (`unspecified`) is unaffected.
   `JARVIS_ALLOW_EMPTY_PROFILE=1` overrides it for wiring tests.

   Under `arch1` the same function prints the mirror-image confirmation — `arch1 baseline —
   profile injection OFF (N chars on disk, deliberately not injected)`. There are two ways
   to serve the wrong architecture, not one: arch2 with an empty profile behaves like the
   baseline, and arch1 still injecting behaves like arch2. Both would stamp their claimed
   condition on every row, and neither is detectable afterwards.

### Arm order (within-subjects design)

Each participant does all three tasks under **both** arms, so order is confounded with
architecture unless it is counterbalanced *and* recorded. Alternate at the desk
(P01: arch1→arch2, P02: arch2→arch1, …) — the code can only record the order, not choose it.

`arch_position` (1 or 2) is stamped on every ratings.jsonl row and every survey CSV row.
It is **derived**, not another env var: at startup the backend checks whether the *other*
arch already has survey rows for this participant. The moderator has two labels to get
right already, and this one is recoverable from data they can't get wrong. It prints in
the startup line (`arm=2 of 2`), so a wrong value is visible before the participant sits
down. Caveat: an arm abandoned before its first "Finish Task" leaves no rows, so the next
arm would also read as position 1.

`--profile-url` is the one code path in reset_user_state.py that imports a Jarvis module
(and therefore needs the venv active, the network, and a Groq key). The import is local to
`seed_profile()` so every other path — including `--status` — stays stdlib-only. Don't
hoist it.

**Sources.** `--profile-url` and `--profile-text-file` are both repeatable and can be
combined. `learn_from_sources()` fetches everything and summarizes it in **one** call —
never one call per source, because the profile has a single `summary` field and per-source
calls would leave only the last one standing. The character budget is split evenly across
sources so a long page can't crowd out a short bio.

`--profile-text-file` is the fallback for a participant with no public URL (the screener
normally excludes them, but it's needed for piloting). It runs the *same* summarizer, so
the stored profile has the same shape — this is the one layer Arch 2 has and it shouldn't
vary in form by participant. `source_type` records `url`, `text`, or `text+url`; those are
not equivalent inputs (written text is what someone chooses to disclose, a public page is
what's already visible) and a result that hinges on the difference should be visible.

Two things the summarizer prompt defends against, both found the hard way:

- **Plain prose, no markdown.** It was emitting bullet lists, which are injected verbatim
  and only under arch2 — pulling Arch 2 toward bulleted replies is a style difference
  perfectly confounded with the arm, in an interface that speaks its answers aloud.
- **Third person, always.** A bio written *about* the participant ("My dad is 54…")
  produced "Your dad is a 54-year-old…", which under "WHAT YOU KNOW ABOUT THE USER" makes
  the assistant think its user is the author rather than the subject. Have participants
  write in first person anyway; the prompt corrects it either way.

Every source must be about the *participant*. Feeding a page about someone else risks the
merge conflating them.

Partial failure is reported, not fatal: one dead URL alongside a working source still
produces a profile, with a loud `!! N of M source(s) FAILED` warning. All sources failing
is fatal (exit 2).

**Label conventions.** Condition is `arch1` or `arch2` (lowercase, matching
architecture.txt). Participant is `P01`-style, capital P, zero-padded. The participant ID
is the only join key between a participant's arch1 and arch2 rows — session IDs are
per-connection and can't pair them — so a variant spelling means reconciling by hand after
data collection. It also breaks `arch_position` derivation, which matches on that string.
Use the same string for `reset_user_state.py --participant P03`.

---

## Paper todos (from advisor)
- [x] Investigate UpTrain for automatic evaluation
- [x] Functionalize/reorganize files
- [x] Improve RAG pipeline grounding
- [x] Fix eval to test personalization-dependent queries
- [ ] Tune hyperparameters (k, similarity threshold for preference retrieval)
- [ ] Plan user study with 5-10 live test subjects
- [ ] Investigate FAISS/ChromaDB for faster preference retrieval (future work)
- [ ] Active learning layer — Jarvis proactively asks profile-filling questions
- [ ] Investigate MCP

---

## What NOT to do
- Do not modify user_profile.json directly — use remember_fact() / forget_fact()
- Do not re-add remembered facts, style, or preference examples to the system prompt, or
  re-bind remember/forget/learn_about_user in tools/__init__.py. Each one is a second
  personalization channel and reintroducing it makes an Arch 2 result unattributable to the
  cold-start profile. If a layer genuinely needs to come back, that's a study-design
  decision. `learn_about_user` is the sharpest of the three — it overwrites the seeded
  summary outright, so a participant volunteering a link mid-session would replace the
  cold start with a warm one, and if that happened in the first arm the second arm would
  run against a different profile.
- Do not hand-edit or delete rows from study_data/survey_responses.csv mid-study — the
  next task number is counted from it, so removing a row makes the following survey
  overwrite that task's slot. Fix it after data collection, not during.
- Do not remove truststore.inject_into_ssl() — will break on this machine
- Do not run full eval (22 queries x 3 ablations = 66 calls) without checking Tavily credit balance first
