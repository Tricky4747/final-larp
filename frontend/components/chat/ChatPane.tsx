"use client";
import { useStore } from "@/lib/store";
import MessageList from "./MessageList";
import IdeaInput from "./IdeaInput";
import PipelineStrip from "./PipelineStrip";

export default function ChatPane({ onChats, onPanel }: { onChats: () => void; onPanel: () => void }) {
  const active = useStore((s) => s.active);
  return (
    <>
      <header className="flex items-center gap-3 border-b border-line bg-panel px-4 py-3">
        <button className="md:hidden text-sm text-mute" onClick={onChats}>Chats</button>
        <h2 className="flex-1 text-sm font-semibold">{active === "group" ? "Group" : active === "founder" ? "Founder" : active}</h2>
        <button className="lg:hidden text-sm text-mute" onClick={onPanel}>Files</button>
      </header>
      <PipelineStrip />
      <MessageList />
      <IdeaInput />
    </>
  );
}
