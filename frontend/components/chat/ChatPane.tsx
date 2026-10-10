"use client";
import { useStore } from "@/lib/store";
import MessageList from "./MessageList";
import Avatar from "../Avatar";
import IdeaInput from "./IdeaInput";
import PipelineStrip from "./PipelineStrip";

const ROLE: Record<string, string> = {
  group: "Whole team", Control: "Orchestrator", Validation: "Market research", Planner: "Strategy and plan",
  LandingPage: "Builds and deploys the page", LeadGen: "Finds leads", Marketing: "Writes the DMs",
};

export default function ChatPane({ onChats, onPanel }: { onChats: () => void; onPanel: () => void }) {
  const active = useStore((s) => s.active);
  const connected = useStore((s) => s.connected);
  const title = active === "group" ? "Group" : active === "founder" ? "Founder" : active;
  return (
    <>
      <header className="flex items-center gap-3 border-b border-line bg-panel px-4 py-3">
        <button className="md:hidden text-sm text-mute" onClick={onChats}>Chats</button>
        <Avatar name={active} size={36} />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold">{title}</h2>
          <p className="truncate text-xs text-mute">{ROLE[active] ?? "Chat"}</p>
        </div>
        <span className="flex items-center gap-1.5 text-xs text-mute" role="status">
          <i className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400" : "bg-red-400"}`} />
          {connected ? "Live" : "Reconnecting"}
        </span>
        <button className="lg:hidden text-sm text-mute" onClick={onPanel}>Files</button>
      </header>
      <PipelineStrip />
      <MessageList />
      <IdeaInput />
    </>
  );
}
