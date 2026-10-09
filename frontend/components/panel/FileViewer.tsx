"use client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore } from "@/lib/store";

export default function FileViewer({ name }: { name: string }) {
  const content = useStore((s) => s.fileContents[name]);
  if (content === undefined) return <p className="p-4 text-sm text-mute">Loading {name}...</p>;
  if (!content.trim()) return <p className="p-4 text-sm text-mute">{name} is empty. It has not been written yet.</p>;
  if (name === "landing.md") {
    const url = content.match(/<!--\s*live:\s*(\S+?)\s*-->/)?.[1];
    return (
      <div className="p-4">
        {url && <a href={url} target="_blank" rel="noopener noreferrer" className="mb-3 block break-all text-sm text-amber underline">{url}</a>}
        <pre className="max-h-96 overflow-auto rounded bg-ink p-3 text-xs">{content}</pre>
      </div>
    );
  }
  const variants = name === "variants.md" ? content.split("\n").map((l) => l.match(/^([A-D]):\s*(.*)$/)).filter(Boolean) as RegExpMatchArray[] : [];
  if (variants.length > 0) {
    return (
      <div className="space-y-2 p-4">
        {variants.map((v) => (
          <div key={v[1]} className="rounded-lg bg-raise p-3">
            <div className="text-xs font-semibold text-amber">Variant {v[1]}</div>
            <p className="mt-1 text-sm">{v[2]}</p>
          </div>
        ))}
      </div>
    );
  }
  return <div className="md overflow-x-auto p-4"><ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown></div>;
}
