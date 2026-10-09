"use client";
import { useStore } from "@/lib/store";
import { STAGES, agentColor } from "@/lib/agentColors";

export default function PipelineStrip() {
  const messages = useStore((s) => s.messages);
  const state = (st: string) => {
    const done = messages.some((m) => m.sender === st && m.channel === "group" && m.kind === "message" && st !== "Control");
    const started = messages.some((m) => m.sender === st);
    return done ? "done" : started ? "active" : "idle";
  };
  return (
    <ol className="flex gap-2 overflow-x-auto border-b border-line bg-ink px-4 py-2 text-xs" aria-label="Pipeline progress">
      {STAGES.map((st) => {
        const s = state(st);
        return (
          <li key={st} className={`flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 ${s === "idle" ? "border-line text-mute" : "border-transparent text-ink"}`}
            style={s === "idle" ? undefined : { background: agentColor(st), opacity: s === "done" ? 1 : 0.7 }}>
            {s === "done" ? "Done" : s === "active" ? "Working" : "Waiting"}: {st}
          </li>
        );
      })}
    </ol>
  );
}
