"use client";
import { useStore } from "@/lib/store";
import { refreshFile } from "@/lib/stream";
import FileViewer from "./FileViewer";

export default function FilesTab() {
  const files = useStore((s) => s.files);
  const flashing = useStore((s) => s.flashing);
  const open = useStore((s) => s.openFile);
  const pick = (f: string) => { useStore.getState().set({ openFile: f }); refreshFile(f); };
  return (
    <div>
      <ul className="border-b border-line">
        {files.length === 0 && <li className="p-4 text-sm text-mute">No files yet. Agents create them as they work.</li>}
        {files.map((f) => (
          <li key={f + (flashing[f] ?? "")} className={flashing[f] ? "flash" : ""}>
            <button onClick={() => pick(f)} className={`w-full px-4 py-2 text-left text-sm ${open === f ? "bg-raise font-medium" : "hover:bg-raise/60"}`}>{f}</button>
          </li>
        ))}
      </ul>
      {open ? <FileViewer name={open} /> : files.length > 0 && <p className="p-4 text-sm text-mute">Select a file to read it.</p>}
    </div>
  );
}
