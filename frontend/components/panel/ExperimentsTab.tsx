"use client";
import { useEffect, useState } from "react";
import { useStore, selectLatestApprovalId } from "@/lib/store";
import { getExperiments, postRound } from "@/lib/api";

const MIN_SENDS = 5;   // backend only names a winner after this many sends

export default function ExperimentsTab() {
  const exp = useStore((s) => s.experiments);
  const messages = useStore((s) => s.messages);
  const autoRounds = useStore((s) => s.autoRounds);
  const batchSize = useStore((s) => s.batchSize);
  const latest = useStore(selectLatestApprovalId);
  const answered = useStore((s) => (latest ? !!s.approvals[latest] : true));
  const [note, setNote] = useState("");
  useEffect(() => {
    let live = true;
    const tick = () => getExperiments().then((e) => live && useStore.getState().set({ experiments: e })).catch(() => {});
    tick(); const id = setInterval(tick, 2000);
    return () => { live = false; clearInterval(id); };
  }, []);

  // Control announces "Retiring variant X": the stats API has no retired flag, so read it from the chat.
  const retired = new Set(messages.flatMap((m) => (m.sender === "Control" ? [...m.text.matchAll(/^Retiring variant (\w)/g)].map((r) => r[1]) : [])));
  const keys = Object.keys(exp).sort();
  const eligible = keys.filter((k) => !retired.has(k) && exp[k].sends >= MIN_SENDS);
  const best = eligible.reduce<string | null>((b, k) => (b === null || exp[k].rate > exp[b].rate ? k : b), null);
  const max = Math.max(0.01, ...keys.map((k) => exp[k].rate));
  const rounds = messages.filter((m) => m.sender === "Control" && /^Round \d+ done/.test(m.text)).length;
  const setBatch = (n: number) => useStore.getState().set({ batchSize: Math.max(1, Math.min(20, n || 1)) });

  const runRound = async () => {
    setNote("");
    try { await postRound(batchSize); setNote(`Round ${rounds + 1} requested. Approve it in the chat to send the DMs.`); useStore.getState().set({ active: "group" }); }
    catch { setNote("Could not start a round. Is the backend running?"); }
  };

  return (
    <div className="space-y-4 p-4">
      {keys.length === 0
        ? <p className="text-sm text-mute">No variants yet. Reply rates per variant appear here once the pipeline reaches Marketing.</p>
        : <p className="text-xs text-mute">Reply rate by DM variant. A winner is named after {MIN_SENDS} sends. Retired variants are greyed out.</p>}
      {keys.map((k) => {
        const v = exp[k]; const lead = k === best; const out = retired.has(k);
        return (
          <div key={k} className={out ? "opacity-50" : ""} aria-label={`Variant ${k}: ${Math.round(v.rate * 100)} percent reply rate${out ? ", retired" : ""}`}>
            <div className="mb-1 flex justify-between text-sm">
              <span className={lead ? "font-semibold text-amber" : ""}>Variant {k}{lead ? " (leading)" : ""}{out ? " (retired)" : ""}</span>
              <span>{Math.round(v.rate * 100)}%</span>
            </div>
            <div className="h-5 rounded bg-raise"><div className="h-5 rounded transition-all duration-500" style={{ width: `${(v.rate / max) * 100}%`, background: lead ? "#e8b84a" : "#5d6b80" }} /></div>
            <div className="mt-1 text-xs text-mute">{v.replies} replies from {v.sends} sends</div>
          </div>
        );
      })}
      <div className="space-y-3 border-t border-line pt-4">
        <div className="flex gap-3">
          <div>
            <label className="mb-1 block text-xs text-mute" htmlFor="batch-n">DMs per round</label>
            <input id="batch-n" type="number" min={1} max={20} value={batchSize} onChange={(e) => setBatch(Number(e.target.value))} className="w-20 rounded bg-raise px-2 py-1 text-sm" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-mute" htmlFor="auto-n">Auto-ask for rounds up to</label>
            <select id="auto-n" value={autoRounds} onChange={(e) => useStore.getState().set({ autoRounds: Number(e.target.value) })} className="rounded bg-raise px-2 py-1 text-sm">
              <option value={1}>Off</option>{[2, 3, 4, 5].map((n) => <option key={n} value={n}>Round {n}</option>)}
            </select>
          </div>
        </div>
        <button onClick={runRound} disabled={!answered} className="rounded bg-amber px-3 py-1 text-sm font-medium text-ink disabled:opacity-40">Run another round now</button>
        {!answered && <p className="text-xs text-mute">Answer the open approval in the chat first.</p>}
        {note && <p className="text-xs text-mute" role="status">{note}</p>}
      </div>
    </div>
  );
}
