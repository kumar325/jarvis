# Himavat

A voice assistant built to answer a research question: **does giving an assistant a
cold-start profile of who you are — scraped once, before you ever speak to it — measurably
change how useful people find it?**

Himavat is a working assistant, not a mock-up. You hold a key, talk, and it answers out
loud: Whisper transcribes, a LangChain agent on Groq reasons and calls tools, and pyttsx3
speaks the reply. It searches the web, cross-checks sources against each other, and manages
files in a sandbox. It runs as a terminal program or as a browser app backed by a
WebSocket server.

It is also the instrument for a study, which is why it is built the way it is. The same
codebase serves both experimental conditions, logs its own sessions, and ships with an
ablation harness for scoring changes offline.

Open source under the [MIT License](LICENSE) — use it, fork it, build on it. If you are
running your own study with it, the design notes in `CLAUDE.md` explain which decisions
are load-bearing and why.

---

## Research context

This assistant was built for a **University of Washington** research study on cold-start
personalization in conversational agents.

**The study involves human subjects and is conducted under approval from the University of
Washington Institutional Review Board.** Participants complete tasks with the assistant
under both conditions and rate the responses. All participant data — transcripts, ratings,
task logs, and the profiles seeded for each person — is written to `study_data/`, which is
**excluded from version control**. No participant data has ever been committed to this
repository, and none should be.

---

## The design

Every participant uses the assistant twice, under two architectures that differ in exactly
one respect:

| | Personalization |
|---|---|
| **Arch 1** (baseline) | None. Generic assistant. |
| **Arch 2** | A profile summary, built before the session from a public URL, bio, or LinkedIn export the participant provides. |

Same model, same base prompt, same tools, same interface, same tasks. The only variable is
whether that profile is injected into the system prompt.

**Both arms are this one repository**, selected by an environment variable, rather than two
forks. That makes "personalization is the only variable" true by construction. With two
repos it would depend on keeping the logging schema, the WebSocket contract, and the UI
byte-identical by hand — and a drifted *instrument* is a worse confound than a drifted
treatment, because it is invisible in the data.

Order is counterbalanced across participants, and which arm ran first is recorded on every
logged row, since order is otherwise confounded with architecture.

Three personalization mechanisms that earlier versions injected — remembered facts, writing-
style mirroring, and retrieved preference examples — were deliberately removed from the
prompt so that any Arch 2 result can be attributed to the cold-start profile alone. They are
still collected on disk for later analysis, and still used by the CLI and the eval harness.

---

## Setup

Requires Python 3.14 and API keys for [Groq](https://console.groq.com) and
[Tavily](https://tavily.com).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` in the repo root:

```
GROQ_API_KEY=...
TAVILY_API_KEY=...
```

Note that `python` on PATH may resolve to the Windows Store stub rather than the venv.
Activate first, or call `.venv\Scripts\python.exe` directly.

The first run downloads the Whisper and sentence-transformers models and takes a few
minutes. Everything after that is cached and works offline apart from the API calls.

---

## Running it

**Terminal.** Enter to talk, `t` to type instead:

```powershell
python jarvis.py
```

**Browser.** Two terminals — backend, then frontend:

```powershell
.venv\Scripts\python.exe -m uvicorn backend.server:app --port 8000
```

```powershell
cd frontend; npm install; npm run dev
```

**A study session.** Reset and seed state once per participant, then label the backend
before starting it. Both variables are read at import, so the server is restarted between
arms and between participants:

```powershell
python reset_user_state.py --participant P03 --profile-url https://... -y

$env:JARVIS_STUDY_CONDITION = "arch2"   # arch1 | arch2
$env:JARVIS_PARTICIPANT_ID  = "P03"
.venv\Scripts\python.exe -m uvicorn backend.server:app --port 8000
```

The backend prints its condition, participant, and arm position at startup, and refuses to
start if it is told to run Arch 2 with an empty profile — that combination would silently
serve the baseline while stamping `arch2` on every logged row, which nothing downstream
could detect afterwards.

---

## How it fits together

```
jarvis.py              terminal loop
backend/               FastAPI WebSocket server for the browser UI
frontend/              Vite + React study interface
config.py              constants, environment, study labels

voice.py               Whisper STT, pyttsx3 TTS, speech normalization
speech_summary.py      shortens a long reply for the speaker only
agent_loop.py          LangChain agent, bounded tool turns, graceful fallback
system_prompt.py       assembles the system prompt (and gates personalization)
tools/                 web search with cross-source verification; sandboxed files

user_profile.py        cold-start profile from URLs, text, or PDF
preferences.py         preference pairs with similarity retrieval
style_tracker.py       rolling writing-style summary

reset_user_state.py    per-participant reset, seeding, and archiving
summarize_session.py   read a session back
inspect_prompt.py      dump the assembled prompt
eval/                  ablation harness and test queries
```

`CLAUDE.md` carries the deeper design rationale — what each decision protects against, and
which ones must not be reversed without a study-design conversation.

---

## Privacy & Data Handling

Himavat collects PII as part of its cold-start personalization feature, including public
profile data (e.g., LinkedIn, GitHub) and conversation content, gathered only from sources
participants explicitly provide. This data is used solely to generate a study participant's
profile and is never sold or shared with third parties. All collection follows an
IRB-approved protocol with informed written consent, and participants may withdraw at any
time. Responses and ratings are anonymized before analysis or publication, and data is
retained only as long as necessary for research purposes. For questions or data removal
requests, contact karankumar90210@gmail.com.

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Karan Kumar.

The license covers the code. It does not cover the study's participant data, none of which
is in this repository.
