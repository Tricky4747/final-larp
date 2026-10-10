"use client";
import { useStore, selectChannels } from "@/lib/store";
import ChatListItem from "./ChatListItem";

export default function Sidebar({ onPick }: { onPick: () => void }) {
  const channels = useStore(selectChannels);
  return (
    <div className="flex w-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-4 py-4">
        <h1 className="text-base font-semibold">Epsilon</h1>
      </div>
      <nav className="flex-1 overflow-y-auto" aria-label="Chats">
        {channels.map((c) => <ChatListItem key={c} channel={c} onPick={onPick} />)}
      </nav>
    </div>
  );
}
