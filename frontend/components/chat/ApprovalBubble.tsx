"use client";
import { useState } from "react";
import { useStore, selectLatestApprovalId } from "@/lib/store";
import { postApprove } from "@/lib/api";
import { refreshFile } from "@/lib/stream";
import FileViewer from "../panel/FileViewer";

const TARGET: Record<string, string> = { verdict: "Validation", plan: "Planner", landing: "LandingPage", variants: "Marketing" };
const target = (stage?: string | null) => (stage && (TARGET[stage] ?? (/^round\d+$/.test(stage) ? "Marketing" : undefined))) || undefined;
const badge = (stage?: string | null) => {
  if (!stage) return "Approval";
  const r = stage.match(/^round(\d+)$/);
  if (r) return `Round ${r[1]}`;
  return { verdict: "Verdict", plan: "Plan", landing: "Landing page", variants: "DM variants", cascade: "Regenerate", restart: "Restart" }[stage] ?? stage;
};

/** Gate stages accept change requests (Cancel = reject with no text = stop). cascade/restart are plain yes/no. */
export default function ApprovalBubble({ id, stage, file }: { id?: string; stage?: string | null; file?: string }) {
  const result = useStore((s) => (id ? s.approvals[id] : undefined));
  const latest = useStore(selectLatestApprovalId) === id;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [fb, setFb] = useState("");
  const [asking, setAsking] = useState(false);
  const [preview, setPreview] = useState(false);
  if (!id) return <p className="mt-2 text-xs text-red-300">Approval request has no id.</p>;
  const plain = stage === "cascade" || stage === "restart";
  const done = !!result || !latest;
  const who = target(stage);
  const act = async (ok: boolean, feedback = "") => {
    setBusy(true); setErr("");
    try {
      await postApprove(id, ok, feedback);
      useStore.getState().setApproval(id, ok ? "approved" : feedback ? "changes" : "rejected");
    } catch { setErr("Could not reach the server. Try again."); setBusy(false); }
  };
  const togglePreview = () => { if (!preview && file) refreshFile(file); setPreview((p) => !p); };
  const label = { approved: "You approved this.", rejected: "You cancelled. The pipeline stopped here.", changes: `You asked for changes${who ? ` from ${who}` : ""}.` }[result ?? "approved"];
  return (
    <div className="mt-2">
      <span className="mb-2 inline-block rounded-full bg-ink px-2 py-0.5 text-[11px] uppercase tracking-wide text-amber">{badge(stage)}</span>
      {file && (
        <div className="mb-2">
          <button className="text-xs text-amber underline" aria-expanded={preview} onClick={togglePreview}>{preview ? "Hide" : "Preview"} {file}</button>
          <button className="ml-3 text-xs text-mute underline" onClick={() => useStore.getState().set({ openFile: file, tab: "files" })}>Open in Files</button>
          {preview && <div className="mt-2 max-h-72 overflow-y-auto rounded bg-ink"><FileViewer name={file} /></div>}
        </div>
      )}
      {!done && !asking && (
        <div className="flex flex-wrap gap-2">
          <button disabled={busy} onClick={() => act(true)} className="rounded bg-amber px-3 py-1 text-sm font-medium text-ink disabled:opacity-40">Approve</button>
          {!plain && <button disabled={busy} onClick={() => setAsking(true)} className="rounded border border-amber px-3 py-1 text-sm text-amber disabled:opacity-40">Request changes</button>}
          <button disabled={busy} onClick={() => act(false)} className="rounded border border-line px-3 py-1 text-sm disabled:opacity-40">{plain ? "No" : "Cancel"}</button>
        </div>
      )}
      {!done && !plain && !asking && <p className="mt-1 text-[11px] text-mute">Cancel stops the pipeline.{who ? ` Changes go to ${who}.` : ""}</p>}
      {!done && asking && (
        <div className="space-y-2">
          <textarea value={fb} onChange={(e) => setFb(e.target.value)} rows={2} aria-label="What should change?"
            placeholder={who ? `What should ${who} change?` : "What should change?"}
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
