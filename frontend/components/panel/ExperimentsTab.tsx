"use client";
import { useEffect, useState } from "react";
import { useStore } from "@/lib/store";
import { getExperiments, postRound } from "@/lib/api";
import { selectLatestApprovalId } from "@/lib/store";

export default function ExperimentsTab() {
  const exp = useStore((s) => s.experiments);
  useEffect(() => {
    let live = true;
    const tick = () => getExperiments().then((e) => live && useStore.getState().set({ experiments: e })).catch(() => {});
    tick(); const id = setInterval(tick, 2000);
    return () => { live = false; clearInterval(id); };
  }, []);
  const [n, setN] = useState(10);
  const [note, setNote] = useState("");
  const latest = useStore(selectLatestApprovalId);
  const answered = useStore((s) => (latest ? !!s.approvals[latest] : true));
  const pending = !answered;
  const runRound = async () => {
    setNote("");
    try { await postRound(n); setNote("Round started. Approve it in the chat to send the DMs."); setTab();}
    catch { setNote("Could not start a round. Is the backend running?"); }
  };
  const setTab = () => useStore.getState().set({ active: "group" });
  const keys = Object.keys(exp).sort();
  const best = keys.reduce<string | null>((b, k) => (exp[k].sends > 0 && (b === null || exp[k].rate > exp[b].rate) ? k : b), null);
  const max = Math.max(0.01, ...keys.map((k) => exp[k].rate));
  if (keys.length === 0) return <p className="p-4 text-sm text-mute">No variants yet. Reply rates per variant appear here once the pipeline reaches Marketing.</p>;
  return (
    <div className="space-y-4 p-4">
      <p className="text-xs text-mute">Reply rate by DM variant. Leader is highlighted.</p>
      {keys.map((k) => {
        const v = exp[k]; const lead = k === best;
        return (
          <div key={k} aria-label={`Variant ${k}: ${Math.round(v.rate * 100)} percent reply rate`}>
            <div className="mb-1 flex justify-between text-sm"><span className={lead ? "font-semibold text-amber" : ""}>Variant {k}{lead ? " (leading)" : ""}</span><span>{Math.round(v.rate * 100)}%</span></div>
            <div className="h-5 rounded bg-raise"><div className="h-5 rounded transition-all duration-500" style={{ width: `${(v.rate / max) * 100}%`, background: lead ? "#e8b84a" : "#5d6b80" }} /></div>
            <div className="mt-1 text-xs text-mute">{v.replies} replies from {v.sends} sends</div>
          </div>
        );
      })}
      <div className="border-t border-line pt-4">
        <label className="mb-1 block text-sm" htmlFor="round-n">DMs in the next round</label>
        <div className="flex gap-2">
          <input id="round-n" type="number" min={1} max={20} value={n} onChange={(e) => setN(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
            className="w-20 rounded bg-raise px-2 py-1 text-sm" />
          <button onClick={runRound} disabled={pending} className="rounded bg-amber px-3 py-1 text-sm font-medium text-ink disabled:opacity-40">Run another round</button>
        </div>
        {pending && <p className="mt-1 text-xs text-mute">Answer the open approval in the chat first.</p>}
        {note && <p className="mt-1 text-xs text-mute" role="status">{note}</p>}
      </div>
    </div>
  );
}
