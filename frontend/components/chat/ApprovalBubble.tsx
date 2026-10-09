"use client";
import { useState } from "react";
import { useStore, selectLatestApprovalId } from "@/lib/store";
import { postApprove } from "@/lib/api";

const stageNames: Record<string, string> = {
  verdict: "Validation review", plan: "Build plan", landing: "Landing page",
  variants: "DM variants", cascade: "Downstream refresh", restart: "Restart project",
};

/** Gate stages accept change requests (reject + text = revise that agent). cascade/restart are plain yes/no. */
export default function ApprovalBubble({ id, stage, file, text, batch, split, winner, replyRate }: {
  id?: string; stage?: string | null; file?: string; text?: string;
  batch?: number; split?: Record<string, number>; winner?: string; replyRate?: number;
}) {
  const result = useStore((s) => (id ? s.approvals[id] : undefined));
  const latest = useStore(selectLatestApprovalId) === id;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [fb, setFb] = useState("");
  const [asking, setAsking] = useState(false);
  if (!id) return <p className="mt-2 text-xs text-red-300">Approval request has no id.</p>;
  const plain = stage === "cascade" || stage === "restart";
  const done = !!result || !latest;
  const round = stage?.startsWith("round");
  const batchMatch = text?.match(/to (\d+) leads?/);
  const parsedBatch = batch ?? (batchMatch ? Number(batchMatch[1]) : undefined);
  const parsedSplit = split ?? Object.fromEntries(Array.from(text?.matchAll(/([A-D]):\s*(\d+)/g) ?? [], (m) => [m[1], Number(m[2])]));
  const act = async (ok: boolean, feedback = "") => {
    setBusy(true); setErr("");
    try {
      await postApprove(id, ok, feedback);
      useStore.getState().setApproval(id, ok ? "approved" : feedback ? "changes" : "rejected");
    } catch { setErr("Could not reach the server. Try again."); setBusy(false); }
  };
  const label = { approved: "You approved this.", rejected: "You rejected this and stopped here.", changes: "You asked for changes." }[result ?? "approved"];
  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-amber/40 bg-ink/70">
      <div className="flex items-start gap-3 border-b border-line px-3 py-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-amber text-sm font-bold text-ink">?</span>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber">Founder approval</p>
          <p className="mt-0.5 text-sm font-semibold text-text">{stageNames[stage ?? ""] ?? (round ? `Outreach ${stage}` : "Pipeline decision")}</p>
        </div>
        {round && <span className="rounded-full bg-raise px-2 py-1 text-[10px] font-medium text-mute">{stage}</span>}
      </div>
      <div className="space-y-3 px-3 py-3">
        {round && (parsedBatch || Object.keys(parsedSplit).length > 0 || winner) && (
          <div className="grid grid-cols-2 gap-2 text-xs">
            {parsedBatch && <div className="rounded-md bg-raise px-2.5 py-2"><span className="block text-[10px] uppercase text-mute">Batch</span><strong>{parsedBatch} DMs</strong></div>}
            {winner && <div className="rounded-md bg-raise px-2.5 py-2"><span className="block text-[10px] uppercase text-mute">Leading</span><strong>Variant {winner}{replyRate != null ? ` · ${(replyRate * 100).toFixed(0)}%` : ""}</strong></div>}
            {Object.keys(parsedSplit).length > 0 && <div className="col-span-2 rounded-md bg-raise px-2.5 py-2"><span className="block text-[10px] uppercase text-mute">Split by variant</span><strong>{Object.entries(parsedSplit).map(([v, count]) => `${v}: ${count}`).join("  ·  ")}</strong></div>}
          </div>
        )}
        {file && <button className="text-xs font-medium text-amber underline decoration-amber/50 underline-offset-2 hover:decoration-amber" onClick={() => useStore.getState().set({ openFile: file, tab: "files" })}>Review {file}</button>}
      {!done && !asking && (
        <div className="flex flex-wrap gap-2">
          <button disabled={busy} onClick={() => act(true)} className="rounded-md bg-amber px-3 py-2 text-sm font-semibold text-ink transition hover:bg-amber/90 disabled:opacity-40">Approve</button>
          {!plain && <button disabled={busy} onClick={() => setAsking(true)} className="rounded-md border border-amber/70 px-3 py-2 text-sm font-medium text-amber transition hover:bg-amber/10 disabled:opacity-40">Request changes</button>}
          <button disabled={busy} onClick={() => act(false)} className="rounded-md border border-line px-3 py-2 text-sm text-mute transition hover:border-red-300 hover:text-red-200 disabled:opacity-40">{plain ? "No" : "Stop"}</button>
        </div>
      )}
      {!done && asking && (
        <div className="space-y-2">
          <textarea autoFocus value={fb} onChange={(e) => setFb(e.target.value)} rows={3} aria-label="What should change?" placeholder="Tell the agent what to revise..."
            className="w-full resize-none rounded-md border border-line bg-raise px-2.5 py-2 text-sm placeholder:text-mute" />
          <div className="flex gap-2">
            <button disabled={busy || !fb.trim()} onClick={() => act(false, fb.trim())} className="rounded-md bg-amber px-3 py-2 text-sm font-semibold text-ink disabled:opacity-40">Send changes</button>
            <button disabled={busy} onClick={() => setAsking(false)} className="rounded-md border border-line px-3 py-2 text-sm">Back</button>
          </div>
        </div>
      )}
      {done && <p className="mt-1 text-xs text-mute">{result ? label : "Already answered."}</p>}
      {err && <p className="mt-1 text-xs text-red-300">{err}</p>}
      </div>
    </div>
  );
}
