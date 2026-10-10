"use client";
import { useState } from "react";
import { useStore } from "@/lib/store";
import { MOCK, postChat, postIdea } from "@/lib/api";

/** First message starts the pipeline (POST /idea). After that, messages go to POST /chat for the open chat;
 *  the backend echoes them over SSE, so they are not added locally. */
export default function IdeaInput() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const active = useStore((s) => s.active);
  const started = useStore((s) => s.ideaSent);
  // Suggested commands only make sense once the first batch of DMs has actually gone out (Control posts "Round N done").
  const firstRoundSent = useStore((s) => s.messages.some((m) => m.sender === "Control" && /^Round \d+ done/.test(m.text)));
  const send = async (override?: string) => {
    const msg = (override ?? text).trim();
    if (!msg || busy) return;
    setBusy(true); setErr("");
    const st = useStore.getState();
    try {
      if (!started) {
        st.addMessage({ id: "f" + Math.random().toString(16).slice(2, 9), ts: Date.now() / 1000, sender: "founder", channel: "group", text: msg, kind: "message", meta: {} });
        st.setActive("group"); setText("");
        await postIdea(msg);
      } else {
        await postChat(msg, active); setText("");
        if (MOCK) st.addMessage({ id: "f" + Math.random().toString(16).slice(2, 9), ts: Date.now() / 1000, sender: "founder", channel: active, text: msg, kind: "message", meta: {} });
      }
    } catch { setErr("Could not reach the backend. Check that it is running on the API URL, then send again."); setText(msg); }
    setBusy(false);
  };
  const who = active === "group" ? "the team" : active;
  const placeholder = !started ? "Describe your business idea"
    : !firstRoundSent ? "Ask a question or request a change"
    : active === "group" || active === "Control" ? 'Ask a question, request a change, "run another round", or "new idea: ..."'
    : `Message ${who}: ask why, or request a change`;
  const chips = started && firstRoundSent && (active === "group" || active === "Control")
    ? ["Run another round", "Set explore to 30%", "Send 5 per round", "Why this audience?"] : [];
  return (
    <div className="border-t border-line bg-panel p-3">
      {err && <p className="mb-2 text-xs text-red-300">{err}</p>}
      {chips.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2" aria-label="Quick actions">
          {chips.map((c) => <button key={c} disabled={busy} onClick={() => send(c)} className="rounded-full border border-line px-3 py-1 text-xs text-mute hover:text-text disabled:opacity-40">{c}</button>)}
        </div>
      )}
      <div className="flex gap-2">
        <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={placeholder} aria-label={started ? "Message" : "Business idea"}
          className="flex-1 rounded-lg bg-raise px-3 py-2 text-sm placeholder:text-mute" />
        <button onClick={() => send()} disabled={busy || !text.trim()} className="rounded-lg bg-amber px-4 text-sm font-medium text-ink disabled:opacity-40">{started ? "Send" : "Send idea"}</button>
      </div>
    </div>
  );
}