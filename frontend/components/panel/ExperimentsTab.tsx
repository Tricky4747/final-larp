"use client";
import { useEffect } from "react";
import { useStore } from "@/lib/store";
import { getExperiments } from "@/lib/api";

export default function ExperimentsTab() {
  const exp = useStore((s) => s.experiments);
  useEffect(() => {
    let live = true;
    const tick = () => getExperiments().then((e) => live && useStore.getState().set({ experiments: e })).catch(() => {});
    tick(); const id = setInterval(tick, 2000);
    return () => { live = false; clearInterval(id); };
  }, []);
  const keys = Object.keys(exp).sort();
  const best = keys.reduce<string | null>((b, k) => (exp[k].sends > 0 && (b === null || exp[k].rate > exp[b].rate) ? k : b), null);
  const max = Math.max(0.01, ...keys.map((k) => exp[k].rate));
  if (keys.length === 0) return <p className="p-4 text-sm text-mute">No DMs sent yet. Reply rates per variant appear here.</p>;
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
    </div>
  );
}
