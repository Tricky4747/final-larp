"use client";
import { useStore } from "@/lib/store";
import { agentColor } from "@/lib/agentColors";

export default function ChatListItem({ channel, onPick }: { channel: string; onPick: () => void }) {
  const active = useStore((s) => s.active === channel);
  const unread = useStore((s) => !!s.unread[channel]);
  const last = useStore((s) => { for (let i = s.messages.length - 1; i >= 0; i--) if (s.messages[i].channel === channel) return s.messages[i]; return null; });
  const label = channel === "group" ? "Group" : channel;
  const color = channel === "group" ? "#e8b84a" : agentColor(channel);
  return (
    <button onClick={() => { useStore.getState().setActive(channel); onPick(); }}
      className={`flex w-full items-center gap-3 px-4 py-3 text-left ${active ? "bg-raise" : "hover:bg-raise/60"}`}>
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-sm font-bold text-ink" style={{ background: color }}>{label[0]}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium">{label}</span>
        <span className="block truncate text-xs text-mute">{last ? last.text : "No messages yet"}</span>
      </span>
      {unread && <span aria-label="Unread messages" className="h-2.5 w-2.5 rounded-full bg-amber" />}
    </button>
  );
}
