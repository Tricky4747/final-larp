import { useStore } from "./store";
import { API, MOCK, getAgents, getFile, getFiles } from "./api";
import { Message } from "./types";
import { MOCK_MESSAGES } from "./mockMessages";

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
        : f.content;
      st.addMessage({
        id: `${output.id}:content`, ts: output.ts, sender: output.sender,
        channel: output.sender, text, kind: "message", meta: {},
      });
    }
  } catch {}
}
function handle(m: Message) {
  const st = useStore.getState();
  const message = m.sender === "Control" && m.kind === "approval_request" && m.channel !== "group"
    ? { ...m, channel: "group" }
    : m;
  if (!st.addMessage(message)) return;
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
