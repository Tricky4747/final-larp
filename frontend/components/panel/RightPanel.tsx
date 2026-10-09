"use client";
import { useStore } from "@/lib/store";
import FilesTab from "./FilesTab";
import ExperimentsTab from "./ExperimentsTab";

export default function RightPanel({ onClose }: { onClose: () => void }) {
  const tab = useStore((s) => s.tab);
  const tabBtn = (t: "files" | "experiments", label: string) => (
    <button role="tab" aria-selected={tab === t} onClick={() => useStore.getState().set({ tab: t })}
      className={`flex-1 py-3 text-sm ${tab === t ? "border-b-2 border-amber font-medium" : "text-mute"}`}>{label}</button>
  );
  return (
    <div className="flex w-full flex-col">
      <div role="tablist" className="flex border-b border-line">
        {tabBtn("files", "Files")}{tabBtn("experiments", "Experiments")}
        <button className="px-3 text-sm text-mute lg:hidden" onClick={onClose}>Close</button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">{tab === "files" ? <FilesTab /> : <ExperimentsTab />}</div>
    </div>
  );
}
