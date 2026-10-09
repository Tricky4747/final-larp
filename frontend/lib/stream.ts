import { useStore } from "./store";
import { API, MOCK, getAgents, getFile, getFiles } from "./api";
import { Message } from "./types";
import { MOCK_MESSAGES } from "./mockMessages";

export async function refreshFiles() {
  try { useStore.getState().set({ files: await getFiles() }); } catch {}
}
export async function refreshFile(name: string) {
  try {
    const f = await getFile(name);
    const st = useStore.getState();
    st.setFile(name, f.content);
    if (!st.files.includes(name)) await refreshFiles();
  } catch {}
}
function handle(m: Message) {
  const st = useStore.getState();
  if (!st.addMessage(m)) return;
  if (m.kind === "file_update" && m.meta?.file) { st.flash(m.meta.file); refreshFile(m.meta.file); }
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
