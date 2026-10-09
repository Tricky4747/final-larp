"use client";
import { useEffect, useRef } from "react";
import { useStore } from "@/lib/store";
import MessageBubble from "./MessageBubble";

export default function MessageList() {
  const active = useStore((s) => s.active);
  const all = useStore((s) => s.messages);
  const msgs = all.filter((m) => m.channel === active);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs.length, active]);
  return (
    <div className="flex-1 space-y-2 overflow-y-auto px-4 py-4" role="log" aria-live="polite">
      {msgs.length === 0 && <p className="mt-16 text-center text-sm text-mute">{active === "group" ? "Describe your business idea below to start the team." : `${active} has not posted yet.`}</p>}
      {msgs.map((m) => <MessageBubble key={m.id} m={m} />)}
      <div ref={end} />
    </div>
  );
}
