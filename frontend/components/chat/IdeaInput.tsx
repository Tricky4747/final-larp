"use client";
import { useState } from "react";
import { useStore } from "@/lib/store";
import { postIdea } from "@/lib/api";

export default function IdeaInput() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const send = async () => {
    const idea = text.trim();
    if (!idea || busy) return;
    setBusy(true); setErr("");
    const st = useStore.getState();
    st.addMessage({ id: "f" + Math.random().toString(16).slice(2, 9), ts: Date.now() / 1000, sender: "founder", channel: "group", text: idea, kind: "message", meta: {} });
    st.setActive("group"); setText("");
    try { await postIdea(idea); }
    catch { setErr("Could not start the pipeline. Check that the backend is running on the API URL, then send the idea again."); setText(idea); }
    setBusy(false);
  };
  return (
    <div className="border-t border-line bg-panel p-3">
      {err && <p className="mb-2 text-xs text-red-300">{err}</p>}
      <div className="flex gap-2">
        <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Describe your business idea" aria-label="Business idea"
          className="flex-1 rounded-lg bg-raise px-3 py-2 text-sm placeholder:text-mute" />
        <button onClick={send} disabled={busy || !text.trim()} className="rounded-lg bg-amber px-4 text-sm font-medium text-ink disabled:opacity-40">Send idea</button>
      </div>
    </div>
  );
}
