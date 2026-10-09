"use client";
import { Message } from "@/lib/types";
import { agentColor } from "@/lib/agentColors";
import { useStore } from "@/lib/store";
import StatusLine from "./StatusLine";
import ApprovalBubble from "./ApprovalBubble";
import LinkCard from "./LinkCard";

export default function MessageBubble({ m }: { m: Message }) {
  if (m.kind === "status") return <StatusLine m={m} />;
  if (m.kind === "file_update") {
    const f = m.meta.file;
    return (
      <div className="pop text-center">
        <button className="rounded-full bg-raise px-3 py-1 text-xs text-mute hover:text-text" disabled={!f}
          onClick={() => f && useStore.getState().set({ openFile: f, tab: "files" })}>
          {m.text}
        </button>
      </div>
    );
  }
  const me = m.sender === "founder";
  return (
    <div className={`pop flex ${me ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[80%] rounded-lg px-3 py-2 ${me ? "bg-mint" : "bg-raise"}`}>
        {!me && <div className="mb-0.5 text-xs font-semibold" style={{ color: agentColor(m.sender) }}>{m.sender}</div>}
        <p className="whitespace-pre-wrap break-words text-sm">{m.text}</p>
        {m.kind === "approval_request" && <ApprovalBubble id={m.meta.id} />}
        {m.meta.url && <LinkCard url={m.meta.url} />}
        <div className="mt-1 text-right text-[10px] text-mute">{new Date(m.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>
      </div>
    </div>
  );
}
