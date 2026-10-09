"use client";
import { useStore, selectChannels } from "@/lib/store";
import ChatListItem from "./ChatListItem";

export default function Sidebar({ onPick }: { onPick: () => void }) {
  const channels = useStore(selectChannels);
  const connected = useStore((s) => s.connected);
  return (
    <div className="flex w-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-4 py-4">
        <h1 className="text-base font-semibold">Agent team</h1>
        <span className="flex items-center gap-1.5 text-xs text-mute" role="status">
          <i className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-red-400"}`} />
          {connected ? "Live" : "Reconnecting"}
        </span>
      </div>
      <nav className="flex-1 overflow-y-auto" aria-label="Chats">
        {channels.map((c) => <ChatListItem key={c} channel={c} onPick={onPick} />)}
      </nav>
    </div>
  );
}
