"use client";
import { useState } from "react";
import { useStore, selectLatestApprovalId } from "@/lib/store";
import { postApprove } from "@/lib/api";

/** Gate stages accept change requests (reject + text = revise that agent). cascade/restart are plain yes/no. */
export default function ApprovalBubble({ id, stage, file }: { id?: string; stage?: string | null; file?: string }) {
  const result = useStore((s) => (id ? s.approvals[id] : undefined));
  const latest = useStore(selectLatestApprovalId) === id;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [fb, setFb] = useState("");
  const [asking, setAsking] = useState(false);
  if (!id) return <p className="mt-2 text-xs text-red-300">Approval request has no id.</p>;
  const plain = stage === "cascade" || stage === "restart";
  const done = !!result || !latest;
  const act = async (ok: boolean, feedback = "") => {
    setBusy(true); setErr("");
    try {
      await postApprove(id, ok, feedback);
      useStore.getState().setApproval(id, ok ? "approved" : feedback ? "changes" : "rejected");
    } catch { setErr("Could not reach the server. Try again."); setBusy(false); }
  };
  const label = { approved: "You approved this.", rejected: "You rejected this and stopped here.", changes: "You asked for changes." }[result ?? "approved"];
  return (
    <div className="mt-2">
      {file && <button className="mb-2 text-xs text-amber underline" onClick={() => useStore.getState().set({ openFile: file, tab: "files" })}>Review {file}</button>}
      {!done && !asking && (
        <div className="flex flex-wrap gap-2">
          <button disabled={busy} onClick={() => act(true)} className="rounded bg-amber px-3 py-1 text-sm font-medium text-ink disabled:opacity-40">Approve</button>
          {!plain && <button disabled={busy} onClick={() => setAsking(true)} className="rounded border border-amber px-3 py-1 text-sm text-amber disabled:opacity-40">Request changes</button>}
          <button disabled={busy} onClick={() => act(false)} className="rounded border border-line px-3 py-1 text-sm disabled:opacity-40">{plain ? "No" : "Reject and stop"}</button>
        </div>
      )}
      {!done && asking && (
        <div className="space-y-2">
          <textarea value={fb} onChange={(e) => setFb(e.target.value)} rows={2} aria-label="What should change?" placeholder="What should change?"
            className="w-full rounded bg-ink px-2 py-1 text-sm placeholder:text-mute" />
          <div className="flex gap-2">
            <button disabled={busy || !fb.trim()} onClick={() => act(false, fb.trim())} className="rounded bg-amber px-3 py-1 text-sm font-medium text-ink disabled:opacity-40">Send changes</button>
            <button disabled={busy} onClick={() => setAsking(false)} className="rounded border border-line px-3 py-1 text-sm">Back</button>
          </div>
        </div>
      )}
      {done && <p className="mt-1 text-xs text-mute">{result ? label : "Already answered."}</p>}
      {err && <p className="mt-1 text-xs text-red-300">{err}</p>}
    </div>
  );
}
