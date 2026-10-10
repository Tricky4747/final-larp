"use client";
import { useStore } from "@/lib/store";
import Avatar from "../Avatar";

export default function ChatListItem({ channel, onPick }: { channel: string; onPick: () => void }) {
  const active = useStore((s) => s.active === channel);
  const unread = useStore((s) => !!s.unread[channel]);
  const last = useStore((s) => { for (let i = s.messages.length - 1; i >= 0; i--) if (s.messages[i].channel === channel) return s.messages[i]; return null; });
  const label = channel === "group" ? "Group" : channel === "founder" ? "Founder" : channel;
  return (
    <button onClick={() => { useStore.getState().setActive(channel); onPick(); }}
      className={`flex w-full items-center gap-3 px-4 py-3 text-left ${active ? "bg-raise" : "hover:bg-raise/60"}`}>
      <Avatar name={channel} size={44} />
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium">{label}</span>
        <span className="block truncate text-xs text-mute">{last ? last.text : "No messages yet"}</span>
      </span>
      {unread && <span aria-label="Unread messages" className="h-2.5 w-2.5 animate-pulse rounded-full bg-amber" />}
    </button>
  );
}
