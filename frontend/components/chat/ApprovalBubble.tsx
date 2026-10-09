"use client";
import { useState } from "react";
import { useStore } from "@/lib/store";
import { postApprove } from "@/lib/api";

export default function ApprovalBubble({ id }: { id?: string }) {
  const result = useStore((s) => (id ? s.approvals[id] : undefined));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  if (!id) return <p className="mt-2 text-xs text-red-300">Approval request has no id.</p>;
  const act = async (ok: boolean) => {
    setBusy(true); setErr("");
    try { await postApprove(id, ok); useStore.getState().setApproval(id, ok ? "approved" : "rejected"); }
    catch { setErr("Could not reach the server. Try again."); setBusy(false); }
  };
  return (
    <div className="mt-2">
      <div className="flex gap-2">
        <button disabled={busy || !!result} onClick={() => act(true)} className="rounded bg-amber px-3 py-1 text-sm font-medium text-ink disabled:opacity-40">Approve</button>
        <button disabled={busy || !!result} onClick={() => act(false)} className="rounded border border-line px-3 py-1 text-sm disabled:opacity-40">Reject</button>
      </div>
      {result && <p className="mt-1 text-xs text-mute">You {result} this.</p>}
      {err && <p className="mt-1 text-xs text-red-300">{err}</p>}
    </div>
  );
}
