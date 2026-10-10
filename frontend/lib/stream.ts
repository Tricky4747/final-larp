import { useStore } from "./store";
import { API, MOCK, getAgents, getFile, getFiles, postRound } from "./api";
import { Message } from "./types";
import { MOCK_MESSAGES } from "./mockMessages";

/** variants.json is {A: {angle, text}, ...}. Show it as readable lines in the agent's own chat. */
export function variantsAsText(content: string): string | null {
  try {
    const o = JSON.parse(content);
    const rows = Object.entries(o).filter(([, v]) => v && typeof (v as { text?: unknown }).text === "string")
      .map(([k, v]) => `${k} (${(v as { angle?: string }).angle ?? "variant"}): ${(v as { text: string }).text}`);
    return rows.length ? rows.join("\n\n") : null;
  } catch { return null; }
}

export async function refreshFiles() {
  try { useStore.getState().set({ files: await getFiles() }); } catch {}
}
export async function refreshFile(name: string, output?: Pick<Message, "id" | "sender" | "ts">) {
  try {
    const f = await getFile(name);
    const st = useStore.getState();
    st.setFile(name, f.content);
    if (!st.files.includes(name)) await refreshFiles();
    if (output && output.sender !== "founder") {
      const text = output.sender === "LandingPage" && name === "landing.md"
        ? f.content.match(/https?:\/\/[^\s<>"')]+/)?.[0] ?? "Landing page link unavailable."
        : name === "variants.json" ? variantsAsText(f.content) ?? f.content
        : f.content;
      st.addMessage({
        id: `${output.id}:content`, ts: output.ts, sender: output.sender,
        channel: output.sender, text, kind: "message", meta: {},
      });
    }
  } catch {}
}
/* Automatically ask for the next outreach round once the previous one has fully finished (incl. learning step).
   Replay-safe: it waits briefly and only fires if no newer approval card exists, so reloading the page never re-triggers it. */
let pendingRound = 0;
let fallback: ReturnType<typeof setTimeout> | undefined;
function tryAuto(n: number, doneTs: number) {
  setTimeout(async () => {
    const st = useStore.getState();
    if (n < 1 || st.autoQueued[n] || n + 1 > st.autoRounds) return;
    if (st.messages.some((x) => x.kind === "approval_request" && x.ts > doneTs)) return;   // already asked (or replaying history)
    st.set({ autoQueued: { ...st.autoQueued, [n]: true } });
    try {
      await postRound(st.batchSize);
      st.addMessage({ id: `auto-${n}`, ts: Date.now() / 1000, sender: "Auto", channel: "group", kind: "status", meta: {},
        text: `Round ${n} finished. Requested round ${n + 1} automatically. Approve it below to send.` });
      if (MOCK) setTimeout(() => handle({ id: `mockr${n + 1}`, ts: Date.now() / 1000, sender: "Control", channel: "group", kind: "approval_request",
        text: `Send round ${n + 1} to ${st.batchSize} leads? Variant D leads at 38%.`, meta: { id: `ap-r${n + 1}`, stage: `round${n + 1}`, file: "variants.json" } }), 800);
    } catch {
      const cur = useStore.getState(); const q = { ...cur.autoQueued }; delete q[n]; cur.set({ autoQueued: q });
    }
  }, 2500);
}
function watchRounds(m: Message) {
  if (m.sender !== "Control" || m.kind !== "message") return;
  const done = m.text.match(/^Round (\d+) done/);
  if (done) {
    pendingRound = Number(done[1]); clearTimeout(fallback);
    fallback = setTimeout(() => tryAuto(pendingRound, m.ts), 45000);   // in case the learning step fails silently
  } else if (m.text.startsWith("Marketing added challenger variants") && pendingRound) {
    clearTimeout(fallback); tryAuto(pendingRound, m.ts);
  }
}
function handle(m: Message) {
  const st = useStore.getState();
  const message = m.sender === "Control" && m.kind === "approval_request" && m.channel !== "group"
    ? { ...m, channel: "group" }
    : m;
  if (!st.addMessage(message)) return;
  watchRounds(message);
  const isAgentOutput = message.sender !== "founder" && message.channel === "group" && message.kind === "message";
  if (isAgentOutput) {
    st.addMessage({ ...message, id: `${message.id}:${message.sender}`, channel: message.sender });
  }
  if (message.kind === "file_update" && message.meta?.file) {
    st.flash(message.meta.file);
    refreshFile(message.meta.file, message);
  }
}

export function startStream(): () => void {
  const st = useStore.getState();
  getAgents().then((a) => st.set({ agents: a.map((x) => x.name) })).catch(() => {});
  refreshFiles();
  if (MOCK) {
    st.set({ connected: true });
    const timers = MOCK_MESSAGES.map((m, i) => setTimeout(() => handle(m), 600 * (i + 1)));
    return () => timers.forEach(clearTimeout);
  }
  const es = new EventSource(API + "/stream");
  es.onopen = () => { useStore.getState().set({ connected: true }); getAgents().then((a) => useStore.getState().set({ agents: a.map((x) => x.name) })).catch(() => {}); };
  es.onerror = () => useStore.getState().set({ connected: false });   // browser auto-reconnects
  es.onmessage = (e) => { try { handle(JSON.parse(e.data)); } catch {} };
  return () => es.close();
}
