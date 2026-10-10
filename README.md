<img width="2172" height="724" alt="White Sigma Ppsilon Logo" src="https://github.com/user-attachments/assets/bf321727-100c-433f-94a9-35093afaac06" />

# Epsilon

> A self-improving team of autonomous AI agents that validates your idea, launches it, and gets better at marketing it with every message.

Built for the hackathon, **Track 1: Autonomous AI Agents**.

## What it does

1. **Validation** researches competitors and pain points and returns a GO / NO-GO verdict.
2. **Planner** writes a plan with design and marketing philosophy.
3. **Control** reads the plan, decides the task list, and dispatches agents in parallel.
4. **LandingPage** builds and deploys a real landing page URL.
5. **LeadGen** finds leads and writes a leads table.
6. **Marketing** writes DM variants (pain-point, social proof, question, offer-first).
7. **Outreach rounds** send personalized DMs to sandboxed test accounts, only after founder approval.
8. **Self-optimizing loop**: an epsilon-greedy bandit sends ~80% of DMs with the best variant and ~20% to new ones. After each round Control writes lessons, and Marketing generates new challenger variants.

The founder approves every important step (Approve / Request changes / Cancel) and can chat with Control or any individual agent at any time.

## Architecture

```
Founder (WhatsApp-style UI)
        |  POST /idea, /chat, /approve   ^  GET /stream (SSE)
        v                                |
   FastAPI  ---  Control (orchestrator, gates, rounds)
                   |
   Validation  Planner  LandingPage  LeadGen  Marketing
                   |
        workspace/*.md  (shared memory)  +  Chroma vector memory
                   |
        SQLite experiments (variant stats)   tools/* (search, deploy, leads, outreach)
```

- **Shared memory**: `workspace/*.md` files (`idea`, `validation`, `plan`, `landing`, `leads`, `variants`, `experiments`, `outreach`, `lessons`, `feedback`). Every write posts a `file_update` message to the chat.
- **Agents** are declarative `AgentSpec`s in `agents/specs.py`. Agents with real tools subclass `Agent` in `agents/custom.py`.
- **LLM**: Gemini via `google-genai`, with retry/backoff and a concurrency semaphore. No API key means **mock mode** with canned output.
- **Vector memory**: Chroma indexes every md file; large files are retrieved by relevance and the retrieval is shown in chat.

## Quick start

```bash
git clone https://github.com/Tricky4747/final-larp
cd <repo>
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Optional: real LLM. Without a key everything runs in mock mode.
export GEMINI_API_KEY=your_key        # or GOOGLE_API_KEY
export MODEL=gemini-2.5-flash         # optional, this is the default

# CLI run (auto-approves all gates)
python run_cli.py

# API server (approval gates enabled)
uvicorn main:app --reload --port 8000
```

Then start the frontend (see `frontend/` or your team's Next.js app) and point it at the API.

> Pre-download the Chroma embedding model before a demo so it does not fetch it over venue Wi-Fi.

### Configuration

| Variable | Purpose | Default |
|---|---|---|
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Enables real LLM calls | unset (mock mode) |
| `MODEL` | Gemini model name | `gemini-2.5-flash` |
| `SIMULATE_REPLIES` | `1` simulates replies with hidden per-variant rates; `0` polls real replies | `1` |

Add any deploy and outreach credentials your tools need (Netlify/Vercel token, Gmail sandbox settings) to your `.env`. Never commit it.

## API

| Endpoint | Purpose |
|---|---|
| `POST /idea {idea}` | Start the pipeline |
| `POST /chat {text, channel}` | Chat with Control (`group`) or an agent (agent name) |
| `POST /approve/{id} {ok, feedback?}` | Answer an approval card |
| `POST /round` | Start another outreach round |
| `POST /replay` / `POST /reset` | Replay a recorded demo run / wipe state |
| `GET /stream` | SSE message stream (replays history, dedupe by `id`) |
| `GET /agents` | Agents and status |
| `GET /files`, `GET /files/{name}` | Workspace files |
| `GET /experiments` | Per-variant sends, replies, reply rate |

**Message schema**

```json
{"id": "...", "ts": "...", "sender": "Control", "channel": "group",
 "text": "...", "kind": "message | file_update | approval_request | status",
 "meta": {"file": "plan.md", "id": "...", "stage": "plan", "url": "..."}}
```

## Approval gates

Gates fire at: verdict (only on NO-GO), plan, landing page, DM variants, and before every DM batch. Options:

- **Approve** continues the pipeline.
- **Request changes** writes your text to `feedback.md` and re-runs the responsible agent (max 5 times).
- **Cancel** stops the pipeline.

Chat revisions can trigger a cascade card to re-run downstream agents (validation → planner → landing, leads, marketing; leads → marketing).

## The learning loop

- Epsilon-greedy bandit: ~80% exploit the best variant, ~20% explore. Explore share is adjustable in chat (5 to 50%).
- A winner is named only after **5+ sends**; before that the UI says "not enough data yet".
- After each round: stats are recorded, Control writes reasoning to `lessons.md`, Marketing creates new challengers (E, F, ...), and losers are retired.
- Upgrade path: Thompson sampling.

## Format contracts between agents

- `leads.md` must contain a table with header `| name | handle | contact | why |`.
- Variants are labeled `A:` to `F:` (and onward) and use `{name}` and `{why}` placeholders.
- Parsing lives in `parsing.py` (`parse_leads`, `parse_variants`) and tolerates bold labels.

## Tools

| Tool | Description |
|---|---|
| `tools/search.py` | `web_search`, `fetch_page` |
| `tools/deploy.py` | `deploy_html` returns a live URL; redeploys update the same site |
| `tools/leads.py` | `find_leads` from a safe public source |
| `tools/outreach.py` | `send_dm` (sandboxed to test handles), `poll_replies` |

## Repo layout

```
main.py            FastAPI app and routes
control.py         Orchestrator, gates, outreach rounds
chat.py            ChatRouter (answer / revise / round / setting / restart)
agent.py           Generic Agent.run()
agents/specs.py    Declarative agent specs and prompts
agents/custom.py   Agents with real tools
bus.py             Message bus and SSE
workspace.py       Shared md files
memory.py          Chroma vector memory
experiments.py     SQLite variant stats and 80/20 allocation
parsing.py         parse_leads, parse_variants
llm.py             Gemini client, retries, JSON parsing
tools/             search, deploy, leads, outreach
run_cli.py         CLI runner
test_gates.py      Approval gate paths
test_chat.py       Chat router checks
smoke_test.sh      End-to-end smoke test
HANDOFF.md         Team contract and per-person instructions
```

## Testing

```bash
python test_gates.py     # 4 approval paths
python test_chat.py      # 10 chat router checks
bash smoke_test.sh       # end-to-end in mock mode
```

`main` must always run in mock mode.

## Safety

- DMs are sent **only to sandboxed test accounts**, never to real leads.
- Every outreach batch needs explicit founder approval.
- Do not commit API keys or `.env` files.

## Known limitations

- The landing page deploys before approval (it redeploys on requested changes).
- Request-changes feedback on a batch changes message wording, not which leads are contacted.
- The first round after the pipeline sends 10 DMs; the batch-size setting applies to rounds started from chat.
- Demo sample sizes are small, so early lessons are hypotheses.

## Team

| Person | Area |
|---|---|
| A | Frontend (Next.js / Tailwind) |
| B | Backend lead: Control, gates, chat, experiments, memory, LLM layer |
| C | Search, deploy, Validation / Planner / LandingPage prompts |
| D | Lead finding, outreach and replies, LeadGen / Marketing prompts |
