"use client";
import { useEffect, useState } from "react";
import Sidebar from "./sidebar/Sidebar";
import ChatPane from "./chat/ChatPane";
import RightPanel from "./panel/RightPanel";
import { startStream } from "@/lib/stream";

export default function AppShell() {
  const [sheet, setSheet] = useState<"chats" | "panel" | null>(null);
  useEffect(() => startStream(), []);
  return (
    <div className="flex h-screen overflow-hidden bg-ink">
      <aside className={`${sheet === "chats" ? "fixed inset-y-0 left-0 z-20 flex" : "hidden"} md:static md:flex w-72 shrink-0 border-r border-line bg-panel`}>
        <Sidebar onPick={() => setSheet(null)} />
      </aside>
      <main className="flex min-w-0 flex-1 flex-col"><ChatPane onChats={() => setSheet("chats")} onPanel={() => setSheet("panel")} /></main>
      <aside className={`${sheet === "panel" ? "fixed inset-y-0 right-0 z-20 flex w-[90vw]" : "hidden"} lg:static lg:flex w-[380px] shrink-0 border-l border-line bg-panel`}>
        <RightPanel onClose={() => setSheet(null)} />
      </aside>
      {sheet && <button aria-label="Close panel" className="fixed inset-0 z-10 bg-black/50 lg:hidden" onClick={() => setSheet(null)} />}
    </div>
  );
}
