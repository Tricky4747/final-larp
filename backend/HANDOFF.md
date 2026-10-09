# Team Handoff: Business Agent Platform

Founder drops an idea → agents validate it, plan it, ship a landing page, find leads, DM them, and learn which DM style works (80% exploit / 20% explore). All agents share state through `workspace/*.md`.

**Everything runs in mock mode with no API keys.** Build your slice against mocks first, then swap in the real thing.

```
cd backend
pip install -r requirements.txt
python run_cli.py                  # whole pipeline, no UI
uvicorn main:app --reload          # API on :8000 for the frontend
export GEMINI_API_KEY=...          # turns on real LLM output (never commit keys)
```

## Branch rules
`git checkout -b feature/<your-thing>`. Pull before you push. Don't edit files you don't own without telling the owner. `agents/specs.py` is shared: edit only your own agent's entry.

| Person | Owns |
|---|---|
| **B** | `bus.py`, `workspace.py`, `agent.py`, `control.py`, `experiments.py`, `main.py`, `llm.py` |
| **A** | `frontend/` |
| **C** | `tools/search.py`, `tools/deploy.py`, Validation / Planner / LandingPage prompts in `agents/specs.py`, `ValidationAgent` + `LandingPageAgent` in `agents/custom.py` |
| **D** | `tools/leads.py`, `tools/outreach.py`, LeadGen / Marketing prompts in `agents/specs.py`, `LeadGenAgent` in `agents/custom.py` |

---

# SHARED CONTRACT (everyone reads this)

## Message schema (what flows through the chat)
```ts
type Message = {
  id: string;            // 8-char unique id
  ts: number;            // unix seconds
  sender: string;        // "founder" | "Control" | "Validation" | "Planner" | "LandingPage" | "LeadGen" | "Marketing"
  channel: string;       // "group" = group chat; otherwise an agent name = that agent's own chat
  text: string;
  kind: "message" | "file_update" | "approval_request" | "status";
  meta: {
    file?: string;       // kind=file_update: which md file changed
    id?: string;         // kind=approval_request: approval id to send to POST /approve/{id}
    url?: string;        // any message may carry a link (e.g. live landing page)
  };
};
```
Meaning of `channel`: **status** messages ("On it...") go to the agent's own chat; results and handoffs go to `group`.

## API
| Method + path | Body | Returns |
|---|---|---|
| `POST /idea` | `{"idea": "..."}` | `{"ok": true}` and starts the pipeline in the background |
| `GET /stream` | none | SSE; each event `data:` is one Message JSON. **Replays full history on connect**, so dedupe by `id` |
| `GET /agents` | none | `[{"name": "Control"}, {"name": "Validation"}, ...]` for the sidebar |
| `GET /files` | none | `["plan.md", "leads.md", ...]` |
| `GET /files/{name}` | none | `{"name": "plan.md", "content": "..."}` |
| `GET /experiments` | none | `{"A": {"sends": 9, "replies": 1, "rate": 0.11}, "B": {...}, ...}` |
| `POST /approve/{id}` | `{"ok": true}` | `{"ok": true}`; unblocks the pipeline. `id` comes from an `approval_request` message's `meta.id` |

CORS is open, so the frontend can call from any port.

## The md files (shared memory)
| File | Written by | Read by | Format rule |
|---|---|---|---|
| `idea.md` | founder | all | free text |
| `validation.md` | Validation | Planner | markdown, must end with `Verdict: GO` or `NO-GO` |
| `plan.md` | Planner | everyone | sections: Audience, Design philosophy, Marketing philosophy, Tasks |
| `landing.md` | LandingPage | none | first line `<!-- live: URL -->`, then the HTML |
| `leads.md` | LeadGen | Marketing, Control | **markdown table with exact header `\| name \| handle \| contact \| why \|`** |
| `variants.md` | Marketing | Control | **4 lines, each starting `A:`, `B:`, `C:`, `D:`** followed by the DM text |
| `experiments.md` | Control | none | appended per round |
| `lessons.md` | Control | Planner, Marketing | appended per round |

Control parses `leads.md` and `variants.md` programmatically, so **the format rules above are not optional.**

## How agents work
An agent is an `AgentSpec` (name, system prompt, files it `reads`, file it `writes`, mock output) in `agents/specs.py`. Generic `Agent.run()` does: status message → `gather()` → LLM call with the md files as context → `finalize()` → write md file → "Done" message.

If your agent needs real tools, subclass `Agent` in `agents/custom.py` and override one or both hooks (the examples are already there):
- `async gather(task) -> str`: call tools (search, scrape) before the LLM. Return text; it's injected into the prompt under `## TOOL RESULTS`.
- `async finalize(out) -> str`: post-process the LLM output (e.g. deploy HTML). Return the text to save.

Register it in the `CUSTOM` dict at the bottom of `agents/custom.py`. Control picks it up automatically.

**Tool rules:** async functions, exact signatures in `tools/*.py`, return mock data when no key is set so teammates aren't blocked, never raise on a failed network call (return empty and let the agent say so in chat), keep every call under ~15 s.

---

# PERSON A: Frontend

**Build:** a WhatsApp-style app (Next.js + Tailwind recommended) on top of the API above.

**Layout**
1. **Left sidebar:** `GET /agents`. Show a "Group" chat on top, then each agent. Show an unread dot when a new message arrives in a chat you're not viewing.
2. **Center chat pane:** messages for the selected channel (`channel === "group"` or `channel === agentName`). Founder messages on the right, agents on the left with name and a color per agent.
3. **Right panel, tab 1: Files.** `GET /files` to list, `GET /files/{name}` to view. Re-fetch a file whenever a `file_update` message arrives with that `meta.file`. Flash the file name briefly so judges see agents writing in real time.
4. **Right panel, tab 2: Experiments.** Poll `GET /experiments` every 2 s. One bar per variant (A-D) showing reply rate, with `sends` and `replies` as labels. Highlight the variant with the highest rate.
5. **Input box:** the founder types the idea → `POST /idea`. Also post it into the chat as a founder message locally.

**Rendering rules by `kind`**
- `message`: normal bubble. If `meta.url` exists, render a link card (this is the live landing page; make it big and clickable).
- `status`: small gray italic line ("Searching competitors...").
- `file_update`: slim system line ("Planner updated plan.md"), clickable to open that file.
- `approval_request`: bubble with **Approve / Reject** buttons → `POST /approve/{meta.id}` with `{"ok": true|false}`. Disable the buttons after click.

**Connecting:** `new EventSource("http://localhost:8000/stream")`. Keep a `Map<id, Message>` and ignore duplicates, because history replays on reconnect.

**Do this first:** build the whole UI against a hardcoded array of fake `Message` objects, then flip to the real stream once Person B confirms the server is up. Polish matters here: this UI is the demo.

**Done when:** you type an idea, watch messages appear across agent chats, see files update live, click Approve, and watch the experiment bars move.

---

# PERSON C: Validation, Planner, Landing Page, web search, deploy

**You build two capabilities and three agent prompts.**

### 1. `tools/search.py`
- `web_search(query, n=5) -> list[{"title","url","snippet"}]`: use Tavily, Brave Search API, SerpAPI, or DuckDuckGo (no key needed). Pick whatever works fastest.
- `fetch_page(url, max_chars=6000) -> str`: `httpx` + `beautifulsoup4`/`readability-lxml`, return clean text.

### 2. `tools/deploy.py`
- `deploy_html(html, site_name) -> str`: publish one self-contained HTML string and return the **live https URL**. Easiest path: Netlify API (create site, upload a zip with `index.html`) or Vercel deployments API. Test it with a real token early, because deploys are the likeliest thing to break on stage.

### 3. Agents (prompts in `agents/specs.py`, tool use in `agents/custom.py`)
- **Validation** (`ValidationAgent.gather` already calls `web_search`): upgrade it to fetch the top 3 competitor pages with `fetch_page`. Prompt must produce: competitors and pricing, top customer pain points (quote real snippets), risks, and a final line `Verdict: GO` or `NO-GO`. Add a surprising finding; it makes the demo memorable.
- **Planner:** turns validation into `plan.md` with Audience, Design philosophy (colors, tone, layout principles), Marketing philosophy (angle, voice, channels), and Tasks. It already reads `lessons.md`, so later loops improve.
- **LandingPage** (`finalize` already deploys): prompt must output **one complete self-contained HTML file** (inline CSS, no external assets, no commentary, no markdown fences) following the plan's design philosophy. Make it look good: hero, 3 benefits, social proof, one clear CTA.

**Deliverable test:** `python run_cli.py` with `GEMINI_API_KEY` set produces a real `validation.md`, `plan.md`, and a live URL in the chat.

**Stretch:** the Skeptic agent (a new spec that reads `plan.md` and posts objections to the group before tasks release; ask Person B to wire it into the pipeline).

---

# PERSON D: Leads, DMs, Marketing, experiments

**You build two capabilities and two agent prompts.**

### 1. `tools/leads.py`
- `find_leads(query, location, n=20) -> list[{"name","handle","contact","source","why"}]`.
- Use a **safe public source**: Google Places API, a public business directory, or an API like Apollo/Hunter. Do **not** scrape logged-in social platforms; they ban fast and it can fail the demo. `handle` is whatever we can message (email, Telegram username, test IG account).

### 2. `tools/outreach.py`
- `send_dm(lead, text) -> {"ok", "id"}`: for the demo, send only to **accounts you control** (a Telegram bot to your own chats or emails to test inboxes is the most reliable). Add a hard guard: refuse to send unless the lead's handle is in an `ALLOWED_TEST_HANDLES` list.
- `poll_replies() -> list[{"handle","variant","text"}]`: returns new replies. Keep a mapping of `handle → variant` when sending so replies can be attributed. If real replies are too slow for the demo, build a **persona simulator** here that replies with different hidden probabilities per variant (Person B's `simulate_reply` is a placeholder for this).

### 3. Agents
- **LeadGen** (`LeadGenAgent.gather` already calls `find_leads`): prompt must output **only** the markdown table with exact header `| name | handle | contact | why |`, and `why` should be a one-line personalization hook per lead (used by Marketing).
- **Marketing:** prompt must output four DM variants labelled `A:`, `B:`, `C:`, `D:` on separate lines with distinct angles: A pain-point, B social-proof, C curiosity question, D offer-first. Keep each under 60 words, personalized with `{name}` and `{why}` placeholders. It reads `lessons.md`, so in later rounds the winning style informs new variants.

**Handoff to B:** once your tools work, tell Person B to replace `simulate_reply` in `control.py` with `send_dm` + `poll_replies`. Control already handles allocation (80/20), approval, and logging.

**Deliverable test:** `find_leads` returns real rows, `send_dm` lands in your test inbox, and a reply flows back through `poll_replies`.

---

# PERSON B (you): checklist
- [ ] Push scaffold; send everyone this file
- [ ] Parse `leads.md` and `variants.md` in `control.py` and use them in `run_round` (replace simulated sends when D's tools are ready)
- [ ] Add Chroma retrieval for `validation.md` / `lessons.md` instead of reading whole files
- [ ] Cache each pipeline stage so a crash resumes instead of restarting
- [ ] Record one full successful run as the demo fallback
